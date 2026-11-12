#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
""" Operate on the MQTTMessageTracker database.

    mqtttracker republish  - republish failed or unconfirmed messages
    mqtttracker prune   - delete confirmed messages before the retention policy does
    mqtttracker status  - show failed and unconfirmed messages and their outcome

    republish and prune are dry runs unless --publish or --delete is given.
    The tracker options are read from the WeeWX config file.
"""

# pylint: disable=wrong-import-order
import argparse
import collections
import fnmatch
import importlib.util
import os
import random
import sys
import threading
import time

# When run as a script, neither the 'user' package nor WeeWX is necessarily on the path.
_bin_root = os.getenv('BIN_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _bin_root not in sys.path:
    sys.path.append(_bin_root)


def _defaults_bindirs(*paths):
    """ The WEEWX_BINDIR values in the distro defaults files, if any. """
    bindirs = []
    for path in paths:
        try:
            with open(path, encoding='utf-8') as file_object:
                for line in file_object:
                    name, separator, value = line.partition('=')
                    if separator and name.strip() == 'WEEWX_BINDIR':
                        bindirs.append(os.path.expanduser(value.strip().strip('"\'')))
        except OSError:
            continue
    return bindirs


def _weewx_bindir():
    """ Where the weewx package is, when the interpreter cannot already import it.

        Extension files live in WEEWX_ROOT/bin/user (for example /etc/weewx/bin/user),
        while the WeeWX code is in BIN_ROOT (/usr/share/weewx), which a script run by
        absolute path does not put on sys.path. """
    candidates = [os.environ.get('WEEWX_BINDIR')]
    candidates.extend(_defaults_bindirs('/etc/default/weewx', '/etc/sysconfig/weewx'))
    candidates.extend(['/usr/share/weewx', '/opt/weewx'])
    for candidate in candidates:
        if candidate and os.path.isdir(os.path.join(os.path.expanduser(candidate), 'weewx')):
            return os.path.expanduser(candidate)
    return None


if importlib.util.find_spec('weewx') is None:
    _bindir = _weewx_bindir()
    if _bindir is None:
        print("mqtttracker: WeeWX is not importable with this Python. Run it with the Python "
              "that WeeWX uses, or set PYTHONPATH to the directory that contains the weewx "
              "package (for a source install, its 'src' directory).", file=sys.stderr)
        sys.exit(2)
    sys.path.insert(0, _bindir)

import weedb  # pylint: disable=wrong-import-position
from weeutil.weeutil import to_bool, to_int  # pylint: disable=wrong-import-position

import user.mqttcommon  # pylint: disable=wrong-import-position
import user.mqttpublish  # pylint: disable=wrong-import-position
import user.mqttmessagetracker  # pylint: disable=wrong-import-position

VERSION = user.mqttpublish.VERSION

# The row helpers are shared with the tracker and the tools.
MESSAGE_COLUMNS = user.mqttmessagetracker.MESSAGE_COLUMNS
decode_payload = user.mqttmessagetracker.decode_payload
next_attempt = user.mqttmessagetracker.next_attempt
insert_attempt = user.mqttmessagetracker.insert_attempt

# An 'inflight' row may still be in flight, and a 'confirmed' row needs no republish.
REPUBLISH_STATUSES = (user.mqttmessagetracker.STATUS_FAILED,
                      user.mqttmessagetracker.STATUS_UNCONFIRMED)
# A prune can also remove the confirmed history, but only when asked to.
PRUNE_STATUSES = REPUBLISH_STATUSES + (user.mqttmessagetracker.STATUS_CONFIRMED,)

# The status command can show any row; the default is every row that is not confirmed.
SUMMARY_STATUSES = (user.mqttmessagetracker.STATUS_FAILED,
                    user.mqttmessagetracker.STATUS_UNCONFIRMED,
                    user.mqttmessagetracker.STATUS_INFLIGHT,
                    user.mqttmessagetracker.STATUS_CONFIRMED)
DEFAULT_SUMMARY_STATUSES = (user.mqttmessagetracker.STATUS_FAILED,
                            user.mqttmessagetracker.STATUS_UNCONFIRMED,
                            user.mqttmessagetracker.STATUS_INFLIGHT)

# Republishing works on the messages that are still unresolved.
DEFAULT_STATUSES = REPUBLISH_STATUSES
# A prune cleans up the messages that were confirmed and no longer need a record.
DEFAULT_PRUNE_STATUSES = (user.mqttmessagetracker.STATUS_CONFIRMED,)

# The republish selection modes.
MODE_AFTER_LAST_SUCCESS = 'after_last_success'
MODE_NEWEST = 'newest'
MODE_ALL = 'all'
DEFAULT_MODE = MODE_AFTER_LAST_SUCCESS

DEFAULT_PLUGIN_SECTION = user.mqttmessagetracker.DEFAULT_PLUGIN_SECTION
# The default page size for prune and status.
DEFAULT_LIMIT = 100
DEFAULT_ACK_TIMEOUT = 10
DEFAULT_CONNECT_TIMEOUT = 10

# The number of rows deleted in one transaction.
_PRUNE_BATCH_SIZE = 100

# What paho returns when it accepted the publish.
_RC_SUCCESS = 0

RepublishOutcome = collections.namedtuple('RepublishOutcome', 'row attempt mid status')


class RepublishError(Exception):
    """ A republish failure. """


class RepublishConfigError(RepublishError):
    """ A configuration or database problem. """


class RepublishConnectError(RepublishError):
    """ The tool could not connect to the broker, nothing was published. """


class PruneError(Exception):
    """ A prune failure. """


class StatusError(Exception):
    """ A status failure. """


def read_config(config_file):
    """ Read the WeeWX config file. """
    try:
        return user.mqttmessagetracker.read_config(config_file)
    except user.mqttmessagetracker.TrackerConfigError as exception:
        raise RepublishConfigError(str(exception)) from exception


# ---------------------------------------------------------------------------
# republish
# ---------------------------------------------------------------------------

def republish_config(config_dict, plugin_section=DEFAULT_PLUGIN_SECTION, data_binding=None, table=None,
                     clientid=None):
    """ Resolve the database, table and mqtt connection options for a republish. """
    try:
        _, database_dict, table_name = user.mqttmessagetracker.tool_config(
            config_dict, plugin_section, data_binding, table)
    except user.mqttmessagetracker.TrackerConfigError as exception:
        raise RepublishConfigError(str(exception)) from exception

    service_dict = dict(config_dict.get('MQTTPublish', {}))
    # Never reuse the service's clientid, the broker would disconnect the running service.
    service_dict.pop('clientid', None)
    if clientid:
        service_dict['clientid'] = clientid
    options = user.mqttpublish.mqtt_connection_options(
        service_dict, default_clientid=f'MQTTPublish-republish-{random.randint(1000, 9999)}')  # NOSONAR - just need a unique id
    return database_dict, table_name, options


def _may_be_on_the_broker(row):
    """ A failed publish is the only row that is certainly not on the broker. """
    return row['status'] != user.mqttmessagetracker.STATUS_FAILED


def _republish_row(chain):
    """ The row to republish for a chain. """
    return user.mqttmessagetracker.chain_anchor(chain)


def _eligible(chain, outcome, statuses, force):
    """ Whether a chain is in a state a republish can still fix.

        'force' also accepts a confirmed chain, so a message with a confirmed attempt can be
        published again on request. """
    if outcome['status'] in statuses:
        return True
    return force and any(row['status'] in statuses for row in chain)


def _newest_per_topic(rows):
    """ When each topic was last written, ignoring the rows certainly not on the broker. """
    newest = {}
    for row in rows:
        if _may_be_on_the_broker(row):
            newest[row['topic']] = max(newest.get(row['topic'], row['published_ts']), row['published_ts'])
    return newest


def _sort_key(row):
    """ The publish order of the selected rows. """
    return row['published_ts'], row['id']


def _candidates(rows, statuses, topic, force):
    """ One row per message chain that passes the filters. """
    statuses = tuple(statuses or DEFAULT_STATUSES)
    candidates = []
    for chain in user.mqttmessagetracker.chain_rows(rows).values():
        outcome = user.mqttmessagetracker.outcome_row(chain)
        if not _eligible(chain, outcome, statuses, force):
            continue
        if topic and not fnmatch.fnmatchcase(outcome['topic'], topic):
            continue
        candidates.append(_republish_row(chain))
    return candidates


def _forced_origins(rows, statuses, force):
    """ The chains selected only because 'force' accepts a confirmed message. """
    if not force:
        return set()
    statuses = tuple(statuses or DEFAULT_STATUSES)
    forced = set()
    for chain in user.mqttmessagetracker.chain_rows(rows).values():
        outcome = user.mqttmessagetracker.outcome_row(chain)
        if outcome['status'] in statuses:
            continue
        if any(row['status'] in statuses for row in chain):
            forced.add(user.mqttmessagetracker.origin_id(chain[0]))
    return forced


def _is_stale(row, newest):
    """ Whether a newer message was published on the row's topic. """
    return row['published_ts'] < newest.get(row['topic'], row['published_ts'])


def _select(candidates, newest, forced=frozenset()):
    """ The candidates that a newer message on the same topic does not make stale.

        'newest' is empty when every candidate is kept. A forced message is always kept. """
    return [row for row in candidates
            if user.mqttmessagetracker.origin_id(row) in forced or not _is_stale(row, newest)]


def _after_last_success(row, forced, last_success_by_topic):
    """ Whether a candidate is kept by the default mode. """
    if user.mqttmessagetracker.origin_id(row) in forced:
        return True
    return user.mqttmessagetracker.is_after_last_success(row, last_success_by_topic)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def select_messages(rows, statuses=None, topic=None, mode=DEFAULT_MODE, force=False):
    """ Select the messages to republish, one row per chain.

        The rows are returned in publish order, oldest first. By default every unresolved message
        published after the last confirmed message on its topic is selected. 'newest' selects only
        the newest unresolved message per topic; 'all' includes messages older than the last
        confirmed message. A confirmed message is skipped unless 'force' is set. """
    candidates = _candidates(rows, statuses, topic, force)
    forced = _forced_origins(rows, statuses, force)
    if mode == MODE_NEWEST:
        candidates = _select(candidates, _newest_per_topic(rows), forced)
    elif mode == MODE_AFTER_LAST_SUCCESS:
        last_success_by_topic = user.mqttmessagetracker.last_success(rows)
        candidates = [row for row in candidates
                      if _after_last_success(row, forced, last_success_by_topic)]
    return sorted(candidates, key=_sort_key)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def superseded(rows, statuses=None, topic=None, force=False, mode=DEFAULT_MODE):
    """ The messages a republish would leave behind.

        In 'newest' mode they are older than a newer message on their topic; in the default
        mode they are older than the last confirmed message. 'all' leaves nothing behind. """
    candidates = _candidates(rows, statuses, topic, force)
    forced = _forced_origins(rows, statuses, force)
    if mode == MODE_ALL:
        return []
    if mode == MODE_NEWEST:
        newest = _newest_per_topic(rows)
        return [row for row in candidates
                if user.mqttmessagetracker.origin_id(row) not in forced and _is_stale(row, newest)]
    last_success_by_topic = user.mqttmessagetracker.last_success(rows)
    return [row for row in candidates
            if not _after_last_success(row, forced, last_success_by_topic)]


def update_attempt(connection, table, row_id, status, timestamp=None):
    """ Record the outcome of a republish. """
    timestamp = time.time() if timestamp is None else timestamp
    if status == user.mqttmessagetracker.STATUS_CONFIRMED:
        statement = f"UPDATE {table} SET status = ?, arrived_ts = ? WHERE id = ?"
    else:
        statement = f"UPDATE {table} SET status = ?, unconfirmed_ts = ? WHERE id = ?"
    with weedb.Transaction(connection) as cursor:
        cursor.execute(statement, (status, timestamp, row_id))


class RepublishClient:  # pylint: disable=too-many-instance-attributes
    """ A paho client that records the message ids the broker acknowledged. """

    def __init__(self, options, ack_timeout=DEFAULT_ACK_TIMEOUT,
                 connect_timeout=DEFAULT_CONNECT_TIMEOUT):
        self.options = options
        self.ack_timeout = ack_timeout
        self.connect_timeout = connect_timeout
        self.api = user.mqttcommon.select_api(options['protocol'])
        self.connected = threading.Event()
        self.connect_rc = None
        self.condition = threading.Condition()
        self.acked = {}

        self.client = user.mqttcommon.create_client(
            self.api, client_id=options['clientid'], protocol=options['protocol'],
            userdata=None, clean_session=True)
        self.client.on_connect = user.mqttcommon.adapt_callback(self.api, 'on_connect', self._on_connect)
        self.client.on_publish = user.mqttcommon.adapt_callback(self.api, 'on_publish', self._on_publish)
        user.mqttcommon.apply_credentials(self.client, options['username'], options['password'])

        tls_dict = options.get('tls')
        if tls_dict and to_bool(tls_dict.get('enable', True)):
            user.mqttcommon.configure_tls(
                self.client, tls_dict,
                format_error=lambda option, value: f"Invalid '{option}', {value}")

    def _on_connect(self, _client, _userdata, _flags, rc, _properties):
        self.connect_rc = rc
        self.connected.set()

    def _on_publish(self, _client, _userdata, mid, _properties):
        with self.condition:
            self.acked[mid] = time.time()
            self.condition.notify_all()

    def connect(self):
        """ Connect and wait for the CONNACK. """
        user.mqttcommon.configure_reconnect_delay(
            self.client, min_delay=self.options['min_delay'], max_delay=self.options['max_delay'])
        try:
            user.mqttcommon.connect(self.client, self.api,
                                    host=self.options['host'], port=self.options['port'],
                                    keepalive=self.options['keepalive'])
        except (OSError, ValueError) as exception:
            raise RepublishConnectError(
                f"Unable to connect to {self.options['host']}:{self.options['port']}: "
                f"{exception}") from exception

        self.client.loop_start()
        if not self.connected.wait(self.connect_timeout):
            self._close()
            raise RepublishConnectError(
                f"No CONNACK from {self.options['host']}:{self.options['port']} within "
                f"{self.connect_timeout} seconds.")
        if self.connect_rc != _RC_SUCCESS:
            self._close()
            raise RepublishConnectError(f"The broker refused the connection, rc {self.connect_rc}.")

    def publish(self, topic, payload, qos, retain):
        """ Hand a message to paho. """
        return self.client.publish(topic, payload, qos=qos, retain=bool(retain))

    def wait_for_ack(self, mid):
        """ Wait for paho to report the message as published, returning when it did or None. """
        with self.condition:
            if self.condition.wait_for(lambda: mid in self.acked, self.ack_timeout):
                return self.acked[mid]
            return None

    def close(self):
        """ Disconnect and stop paho's network loop. """
        self._close()

    def _close(self):
        self.client.disconnect()
        self.client.loop_stop()


def republish_message(client, connection, table, row, clientid):
    """ Publish one message and record its outcome. """
    try:
        payload = decode_payload(row)
    except ValueError as exception:
        raise RepublishConfigError(
            f"Unable to decode the payload of {row['id']}: {exception}") from exception

    message_info = client.publish(row['topic'], payload, row['qos'], row['retain'])
    row_id, attempt, status = insert_attempt(
        connection, table, row, message_info.mid, int(message_info.rc), time.time(), clientid)

    if status == user.mqttmessagetracker.STATUS_FAILED:
        return RepublishOutcome(row, attempt, message_info.mid, status)

    arrived_ts = client.wait_for_ack(message_info.mid)
    if arrived_ts is None:
        status = user.mqttmessagetracker.STATUS_UNCONFIRMED
        update_attempt(connection, table, row_id, status)
    else:
        status = user.mqttmessagetracker.STATUS_CONFIRMED
        update_attempt(connection, table, row_id, status, arrived_ts)
    return RepublishOutcome(row, attempt, message_info.mid, status)


def print_outcomes(outcomes, out):
    """ Print what the broker acknowledged. """
    for outcome in outcomes:
        print(f"  {outcome.status:<12} {outcome.row['topic']} attempt={outcome.attempt} "
              f"mid={outcome.mid}", file=out)


def _print_hidden(rows, statuses, topic, force, mode, out):
    """ Print the messages the selection mode leaves behind. """
    if mode == MODE_ALL:
        return
    hidden = superseded(rows, statuses=statuses, topic=topic, force=force, mode=mode)
    if not hidden:
        return
    if mode == MODE_NEWEST:
        reason = "are older than a newer message on their topic"
    else:
        reason = "are older than the last confirmed message on their topic"
    print(f"{len(hidden)} message(s) {reason}, use --all to republish them.", file=out)


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
def republish(database_dict, table, options, *, statuses=None,
              topic=None, mode=DEFAULT_MODE, force=False, dry_run=True,
              ack_timeout=DEFAULT_ACK_TIMEOUT, connect_timeout=DEFAULT_CONNECT_TIMEOUT, out=None):
    """ Republish the selected messages, returning the selection and the outcomes.

        Nothing is published when 'dry_run' is set, or when nothing is selected. """
    out = sys.stdout if out is None else out
    try:
        connection = weedb.connect(database_dict)
    except weedb.DatabaseError as exception:
        raise RepublishConfigError(
            f"Unable to open the message tracker database: {exception}") from exception

    try:
        rows = user.mqttmessagetracker.fetch_rows(connection, table)
        selected = select_messages(rows, statuses=statuses, topic=topic,
                                   mode=mode, force=force)
        user.mqttmessagetracker.print_plan(selected, out)
        _print_hidden(rows, statuses, topic, force, mode, out)
        if dry_run or not selected:
            return selected, []

        client = RepublishClient(options, ack_timeout=ack_timeout, connect_timeout=connect_timeout)
        client.connect()
        try:
            outcomes = [republish_message(client, connection, table, row, options['clientid'])
                        for row in selected]
        finally:
            client.close()
    except weedb.DatabaseError as exception:
        raise RepublishConfigError(
            f"Unable to use the message tracker table {table}: {exception}") from exception
    finally:
        connection.close()

    print_outcomes(outcomes, out)
    return selected, outcomes


# ---------------------------------------------------------------------------
# prune
# ---------------------------------------------------------------------------

def _is_old_enough(row, retention, now):
    """ Whether the row is older than its retention. A retention of 0 keeps it forever. """
    if retention <= 0:
        return False
    return row['published_ts'] < now - retention


def _chain_row(chain_id, chain, outcome):
    """ The row a prune plan shows for a message: the chain id, its outcome and the payload. """
    row = dict(user.mqttmessagetracker.chain_anchor(chain))
    row.update(id=chain_id, status=outcome['status'], published_ts=outcome['published_ts'],
               row_count=len(chain))
    return row


def _wanted(outcome, statuses, topic):
    """ Whether a chain outcome passes the status and topic filters. """
    if outcome['status'] not in statuses:
        return False
    if topic and not fnmatch.fnmatchcase(outcome['topic'], topic):
        return False
    return True


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _configured_retention(outcome, topic_retention, default_retention,
                          confirmed_topic_retention, confirmed_default_retention):
    """ The retention configured for a chain outcome's status and topic. """
    return user.mqttmessagetracker.chain_retention(
        outcome, confirmed_default_retention, confirmed_topic_retention,
        default_retention, topic_retention)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _old_enough(outcome, older_than, topic_retention, default_retention,
                confirmed_topic_retention, confirmed_default_retention, now):
    """ Whether a chain outcome is older than the retention that applies to it. """
    if older_than == 0:
        return True
    if older_than is not None:
        return _is_old_enough(outcome, older_than, now)
    retention = _configured_retention(outcome, topic_retention, default_retention,
                                      confirmed_topic_retention, confirmed_default_retention)
    return _is_old_enough(outcome, retention, now)


def _chain_outcomes(rows):
    """ The chain id, its rows and its outcome for each message. """
    for chain_id, chain in user.mqttmessagetracker.chain_rows(rows).items():
        yield chain_id, chain, user.mqttmessagetracker.outcome_row(chain)


def _prune_defaults(statuses, topic_retention, default_retention,
                    confirmed_topic_retention, confirmed_default_retention):
    """ Fill in the default statuses and retentions. """
    return (tuple(statuses or DEFAULT_PRUNE_STATUSES),
            topic_retention or {},
            user.mqttmessagetracker.DEFAULT_ERROR_RETENTION
            if default_retention is None else default_retention,
            confirmed_topic_retention or {},
            user.mqttmessagetracker.DEFAULT_CONFIRMED_RETENTION
            if confirmed_default_retention is None else confirmed_default_retention)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def select_chains(rows, statuses=None, topic_retention=None, default_retention=None,
                  confirmed_topic_retention=None, confirmed_default_retention=None,
                  older_than=None, topic=None, limit=DEFAULT_LIMIT, now=None):
    """ Select the messages to delete, oldest first.

        A message is selected when the outcome of its chain has one of the statuses and is
        older than the retention for that status: 'confirmed_retention' for a confirmed
        message, 'error_retention' while it is unresolved. An explicit 'older_than' overrides
        the configured retention; 'older_than=0' selects every matching message, unlike a
        configured retention of 0. """
    (statuses, topic_retention, default_retention,
     confirmed_topic_retention, confirmed_default_retention) = _prune_defaults(
         statuses, topic_retention, default_retention,
         confirmed_topic_retention, confirmed_default_retention)
    now = time.time() if now is None else now

    selected = [_chain_row(chain_id, chain, outcome)
                for chain_id, chain, outcome in _chain_outcomes(rows)
                if _wanted(outcome, statuses, topic) and
                _old_enough(outcome, older_than, topic_retention, default_retention,
                            confirmed_topic_retention, confirmed_default_retention, now)]

    selected.sort(key=lambda row: (row['published_ts'], row['id']))
    return _apply_limit(selected, limit)


def _apply_limit(rows, limit):
    """ The oldest messages up to the limit, or every message when the limit is unset. """
    if limit is None or limit <= 0:
        return rows
    return rows[:limit]


def _outcome_status(connection, table, chain_id):
    """ The current outcome status of a chain, or None when it is gone. """
    columns = ', '.join(user.mqttmessagetracker.CHAIN_COLUMNS)
    cursor = connection.cursor()
    try:
        cursor.execute(f"SELECT {columns} FROM {table} WHERE id = ? OR origin_id = ?",
                       (chain_id, chain_id))
        rows = [dict(zip(user.mqttmessagetracker.CHAIN_COLUMNS, row)) for row in cursor]
    finally:
        cursor.close()
    if not rows:
        return None
    return user.mqttmessagetracker.outcome_row(rows)['status']


def delete_chains(connection, table, rows):
    """ Delete the selected message chains.

        A chain is the original row and its republish attempts. A chain whose outcome changed after it
        was selected is left alone, and a row still in flight ('inflight') is left for the startup
        sweep. """
    deleted = 0
    for start in range(0, len(rows), _PRUNE_BATCH_SIZE):
        chunk = rows[start:start + _PRUNE_BATCH_SIZE]
        with weedb.Transaction(connection) as cursor:
            unchanged = [row['id'] for row in chunk
                         if _outcome_status(connection, table, row['id']) == row['status']]
            deleted += user.mqttmessagetracker.delete_chains(cursor, table, unchanged)
    return deleted


def _retention_option(plugin_dict, option, default_retention):
    """ One configured retention, falling back to its default. """
    retention = to_int(plugin_dict.get(option, default_retention))
    return default_retention if retention is None else retention


def prune_config(config_dict, plugin_section=DEFAULT_PLUGIN_SECTION, data_binding=None, table=None):
    """ Resolve the database, table and retention options to prune by. """
    try:
        plugin_dict, database_dict, table_name = user.mqttmessagetracker.tool_config(
            config_dict, plugin_section, data_binding, table)
    except user.mqttmessagetracker.TrackerConfigError as exception:
        raise PruneError(str(exception)) from exception

    error_retention = _retention_option(
        plugin_dict, 'error_retention', user.mqttmessagetracker.DEFAULT_ERROR_RETENTION)
    confirmed_retention = _retention_option(
        plugin_dict, 'confirmed_retention', user.mqttmessagetracker.DEFAULT_CONFIRMED_RETENTION)

    topic_dicts = plugin_dict.get('topics')
    topic_error_retention = {}
    topic_confirmed_retention = {}
    if topic_dicts:
        topic_error_retention = user.mqttmessagetracker.topic_error_retentions(
            topic_dicts, error_retention)
        topic_confirmed_retention = user.mqttmessagetracker.topic_confirmed_retentions(
            topic_dicts, confirmed_retention)
    return (database_dict, table_name,
            topic_error_retention, error_retention,
            topic_confirmed_retention, confirmed_retention)


def prune(config_dict, options, out=None):
    """ Select the messages and, when asked to, delete them. """
    out = sys.stdout if out is None else out
    (database_dict, table, topic_error_retention, error_retention,
     topic_confirmed_retention, confirmed_retention) = prune_config(
         config_dict, options.plugin_section, options.data_binding, options.table)

    try:
        connection = weedb.connect(database_dict)
    except weedb.DatabaseError as exception:
        raise PruneError(f"Unable to open the message tracker database: {exception}") from exception

    try:
        rows = user.mqttmessagetracker.fetch_rows(connection, table)
        matches = select_chains(rows, statuses=options.status,
                                topic_retention=topic_error_retention,
                                default_retention=error_retention,
                                confirmed_topic_retention=topic_confirmed_retention,
                                confirmed_default_retention=confirmed_retention,
                                older_than=options.older_than,
                                topic=options.topic, limit=0)
        selected = _apply_limit(matches, options.limit)
        row_count = sum(row['row_count'] for row in selected)
        user.mqttmessagetracker.print_plan(selected, out, row_count)
        if len(selected) < len(matches):
            print(f"Selected the oldest {len(selected)} of {len(matches)} message(s); "
                  "use --limit 0 to select all.", file=out)
        if not options.delete or not selected:
            return selected
        deleted = delete_chains(connection, table, selected)
    except weedb.DatabaseError as exception:
        raise PruneError(f"Unable to use the message tracker table {table}: {exception}") from exception
    finally:
        connection.close()

    print(f"Deleted {deleted} row(s).", file=out)
    return selected


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

# The columns the status summary needs; the republish counts are computed per chain.
_STATUS_ROWS_SQL = """
SELECT id, topic, status, published_ts, origin_id, attempt
FROM {table}
"""
_STATUS_COLUMNS = ('id', 'topic', 'status', 'published_ts', 'origin_id', 'attempt')

_STATUS_MESSAGE_SQL = """
SELECT {columns}
FROM {table}
WHERE id = ? OR origin_id = ?
ORDER BY published_ts
"""


def _rows(connection, statement, args=(), columns=None):
    """ Run a query and return its rows, as mappings when the columns are given. """
    cursor = connection.cursor()
    try:
        cursor.execute(statement, args)
        rows = cursor.fetchall()
    finally:
        cursor.close()
    if columns is None:
        return rows
    return [dict(zip(columns, row)) for row in rows]


def _status_chains(rows):
    """ Yield one summary row per message chain.

        The chain is anchored at its original row; if the original was pruned, the oldest
        surviving attempt is the anchor. The current status is the outcome's status. """
    for chain in user.mqttmessagetracker.chain_rows(rows).values():
        anchor = user.mqttmessagetracker.chain_anchor(chain)
        outcome = user.mqttmessagetracker.outcome_row(chain)
        attempts = sum(1 for row in chain if row['attempt'] is not None)
        confirmed = sum(1 for row in chain if row['attempt'] is not None and
                        row['status'] == user.mqttmessagetracker.STATUS_CONFIRMED)
        yield (anchor['id'], anchor['topic'], anchor['status'], anchor['published_ts'],
               attempts, confirmed, outcome['status'])


def status_summary(connection, table, statuses=None, topic=None, limit=DEFAULT_LIMIT):
    """ One row per message chain, with the outcome of its republish attempts. """
    statuses = tuple(statuses or DEFAULT_SUMMARY_STATUSES)
    rows = [row for row in _status_chains(
        _rows(connection, _STATUS_ROWS_SQL.format(table=table), columns=_STATUS_COLUMNS))
        if row[6] in statuses]
    rows.sort(key=lambda row: (row[3], row[0]))
    if topic:
        rows = [row for row in rows if fnmatch.fnmatchcase(row[1], topic)]
    if limit is not None and limit > 0:
        rows = rows[:limit]
    return rows


def status_message(connection, table, message_id):
    """ The chain for a message id, anchored at its original row. """
    message = _rows(connection, f"SELECT id, origin_id FROM {table} WHERE id = ?", (message_id,))
    if not message:
        return []
    chain_id = message[0][1] or message[0][0]
    rows = _rows(connection, _STATUS_MESSAGE_SQL.format(
        columns=', '.join(MESSAGE_COLUMNS), table=table), (chain_id, chain_id))
    return [dict(zip(MESSAGE_COLUMNS, row)) for row in rows]


def _published_at(timestamp):
    """ A published_ts as a readable local time. """
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))


def _message_id(value):
    """ The row id, accepting the 'id=' label the plan and log print. """
    if value[:3].lower() == 'id=':
        return value[3:]
    return value


def print_status_summary(rows, out, statuses=DEFAULT_SUMMARY_STATUSES):
    """ Print the selected messages as a table. """
    if tuple(statuses) == DEFAULT_SUMMARY_STATUSES:
        empty = "No not-confirmed messages."
        label = "not confirmed message(s)"
    else:
        status_text = ', '.join(statuses)
        empty = f"No messages with current status {status_text}."
        label = f"message(s) with current status {status_text}"
    if not rows:
        print(empty, file=out)
        return
    print(f"{len(rows)} {label}:", file=out)
    print(f"  {'ID':<32} {'TOPIC':<30} {'ORIGINAL STATUS':<15} {'ORIGINALLY PUBLISHED':<20}  "
          f"{'ATTEMPTS':<8} {'CONFIRMED':<9}  CURRENT STATUS", file=out)
    for row_id, topic, status, published_ts, attempts, confirmed_attempts, current_status in rows:
        print(f"  {row_id:<32} {topic[:30]:<30} {status:<15} {_published_at(published_ts):<20} "
              f"{attempts:<8} {confirmed_attempts:<9}  {current_status}", file=out)


def print_status_message(rows, message_id, out):
    """ Print one message and its republish attempts. """
    if not rows:
        print(f"No rows found for message {message_id}.", file=out)
        return False
    print(f"Rows for message {message_id}:", file=out)
    for row in rows:
        line = user.mqttmessagetracker.describe_row(row, include_payload=False)
        if row['origin_id']:
            line = f"{line} attempt={row['attempt']} origin={row['origin_id']}"
        print(f"  {line}", file=out)
    return True


def show_status(config_dict, options, out=None):
    """ Show tracked messages and their republish outcome. """
    out = sys.stdout if out is None else out
    try:
        _, database_dict, table = user.mqttmessagetracker.tool_config(
            config_dict, options.plugin_section, options.data_binding, options.table)
    except user.mqttmessagetracker.TrackerConfigError as exception:
        raise StatusError(str(exception)) from exception

    try:
        connection = weedb.connect(database_dict)
    except weedb.DatabaseError as exception:
        raise StatusError(f"Unable to open the message tracker database: {exception}") from exception

    try:
        if options.message:
            message_id = _message_id(options.message)
            rows = status_message(connection, table, message_id)
            return print_status_message(rows, message_id, out)
        rows = status_summary(connection, table, statuses=options.status,
                              topic=options.topic, limit=options.limit)
        print_status_summary(rows, out, options.status)
        return True
    except weedb.DatabaseError as exception:
        raise StatusError(f"Unable to use the message tracker table {table}: {exception}") from exception
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------

def _status_list(value, allowed):
    """ Parse a comma-separated list of statuses. """
    statuses = [status.strip() for status in value.split(',') if status.strip()]
    invalid = [status for status in statuses if status not in allowed]
    if invalid:
        raise argparse.ArgumentTypeError(
            f"invalid status(es) {', '.join(invalid)}, choose from {', '.join(allowed)}")
    return statuses


def _republish_statuses(value):
    """ Parse the statuses a message can be republished from. """
    return _status_list(value, REPUBLISH_STATUSES)


def _prune_statuses(value):
    """ Parse the statuses a row can be pruned from. """
    return _status_list(value, PRUNE_STATUSES)


def _summary_statuses(value):
    """ Parse the statuses the status summary can show. """
    return _status_list(value, SUMMARY_STATUSES)


def _add_tracker_options(parser):
    """ The options that select the tracker config, database and table. """
    parser.add_argument('--plugin-section', default=DEFAULT_PLUGIN_SECTION,
                        help=(f"The config section of the tracker plugin. "
                              f"Default is {DEFAULT_PLUGIN_SECTION}."))
    parser.add_argument('--data-binding', default=None,
                        help="Override the tracker's data_binding option.")
    parser.add_argument('--table', default=None,
                        help="Override the tracker's table option.")


def _add_republish_parser(subparsers):
    """ The republish subcommand. """
    parser = subparsers.add_parser(
        'republish',
        description="Republish the MQTT messages the message tracker recorded.",
        epilog="Without --publish the selection is only printed, nothing is published.")
    _add_tracker_options(parser)
    parser.add_argument('--clientid', default=None,
                        help="The clientid to connect with. Default is a unique MQTTPublish-republish id.")
    parser.add_argument('--status', type=_republish_statuses, default=list(DEFAULT_STATUSES),
                        metavar='STATUS',
                        help=(f"The statuses to republish, comma separated. "
                              f"Default is {', '.join(DEFAULT_STATUSES)}. Choose from "
                              f"{', '.join(REPUBLISH_STATUSES)}."))
    parser.add_argument('--topic', default=None, metavar='GLOB',
                        help="Only republish topics that match the glob, for example 'weather/outTemp_*'.")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--all', action='store_true',
                            help=("Republish every unresolved message, including those older "
                                  "than the last confirmed message on their topic."))
    mode_group.add_argument('--newest', action='store_true',
                            help="Republish only the newest unresolved message per topic.")
    parser.add_argument('--force', action='store_true',
                        help="Republish messages that already have a confirmed attempt.")
    parser.add_argument('--publish', action='store_true',
                        help="Publish the selected messages. Without it nothing is published.")
    parser.add_argument('--ack-timeout', type=float, default=DEFAULT_ACK_TIMEOUT, metavar='SECONDS',
                        help=f"How long to wait for each publish to be acknowledged. "
                             f"Default is {DEFAULT_ACK_TIMEOUT}.")
    parser.add_argument('--connect-timeout', type=float, default=DEFAULT_CONNECT_TIMEOUT, metavar='SECONDS',
                        help=f"How long to wait for the connection. Default is {DEFAULT_CONNECT_TIMEOUT}.")
    return parser


def _add_prune_parser(subparsers):
    """ The prune subcommand. """
    parser = subparsers.add_parser(
        'prune',
        description="Delete confirmed messages before the retention policy does.",
        epilog="Without --delete the selection is only printed, nothing is removed.")
    _add_tracker_options(parser)
    parser.add_argument('--status', type=_prune_statuses, default=list(DEFAULT_PRUNE_STATUSES),
                        metavar='STATUS',
                        help=(f"The statuses to prune, comma separated. "
                              f"Default is {', '.join(DEFAULT_PRUNE_STATUSES)}. Choose from "
                              f"{', '.join(PRUNE_STATUSES)}."))
    parser.add_argument('--older-than', type=int, default=None, metavar='SECONDS',
                        help=("Only prune messages older than SECONDS. Default is the retention "
                              "for the message's status: confirmed_retention for confirmed "
                              "messages, error_retention otherwise."))
    parser.add_argument('--topic', default=None, metavar='GLOB',
                        help="Only prune topics that match the glob, for example 'weather/outTemp_*'.")
    parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT, metavar='COUNT',
                        help=f"The maximum number of messages to prune. Default is {DEFAULT_LIMIT}.")
    parser.add_argument('--delete', action='store_true',
                        help="Delete the selected messages. Without it nothing is removed.")
    return parser


def _add_status_parser(subparsers):
    """ The status subcommand. """
    parser = subparsers.add_parser(
        'status',
        description="Show tracked messages and their republish outcome.")
    _add_tracker_options(parser)
    parser.add_argument('--status', type=_summary_statuses, default=list(DEFAULT_SUMMARY_STATUSES),
                        metavar='STATUS',
                        help=(f"The statuses to show, comma separated. "
                              f"Default is {', '.join(DEFAULT_SUMMARY_STATUSES)}. Choose from "
                              f"{', '.join(SUMMARY_STATUSES)}."))
    parser.add_argument('--message', '--id', dest='message', default=None, metavar='ID',
                        help="Show one message and its republish attempts, using the id from the log.")
    parser.add_argument('--topic', default=None, metavar='GLOB',
                        help="Only messages whose topic matches the glob.")
    parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT, metavar='COUNT',
                        help=f"The maximum number of messages to show. Default is {DEFAULT_LIMIT}.")
    return parser


def build_parser():
    """ The command line parser. """
    parser = argparse.ArgumentParser(
        prog='mqtttracker',
        description="Operate on the MQTTMessageTracker database.")
    parser.add_argument('--config', required=True,
                        help="The WeeWX config file, for example /etc/weewx/weewx.conf.")
    parser.add_argument('--version', action='version', version=f'%(prog)s {VERSION}')

    subparsers = parser.add_subparsers(dest='command', required=True, title='commands')
    _add_republish_parser(subparsers)
    _add_prune_parser(subparsers)
    _add_status_parser(subparsers)
    return parser


def _run_republish(options, out, err):
    """ Run the republish command. """
    try:
        config_dict = read_config(options.config)
        database_dict, table, mqtt_options = republish_config(
            config_dict, options.plugin_section, options.data_binding, options.table, options.clientid)
        _, outcomes = republish(
            database_dict, table, mqtt_options, out=out,
            statuses=options.status, topic=options.topic,
            mode=(MODE_ALL if options.all else
                  MODE_NEWEST if options.newest else
                  MODE_AFTER_LAST_SUCCESS),
            force=options.force, dry_run=not options.publish,
            ack_timeout=options.ack_timeout, connect_timeout=options.connect_timeout)
    except RepublishConnectError as exception:
        print(f"mqtttracker republish: {exception}", file=err)
        return 1
    except RepublishConfigError as exception:
        print(f"mqtttracker republish: {exception}", file=err)
        return 2

    if not outcomes:
        return 0
    confirmed = all(outcome.status == user.mqttmessagetracker.STATUS_CONFIRMED for outcome in outcomes)
    return 0 if confirmed else 1


def _run_prune(options, out, err):
    """ Run the prune command. """
    try:
        config_dict = user.mqttmessagetracker.read_config(options.config)
        prune(config_dict, options, out)
    except (user.mqttmessagetracker.TrackerConfigError, PruneError) as exception:
        print(f"mqtttracker prune: {exception}", file=err)
        return 2
    return 0


def _run_status(options, out, err):
    """ Run the status command. """
    try:
        config_dict = user.mqttmessagetracker.read_config(options.config)
        found = show_status(config_dict, options, out)
    except (user.mqttmessagetracker.TrackerConfigError, StatusError) as exception:
        print(f"mqtttracker status: {exception}", file=err)
        return 2
    return 0 if found else 1


def run(options, out=None, err=None):
    """ Run a command, returning the exit code. """
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    if options.command == 'republish':
        return _run_republish(options, out, err)
    if options.command == 'prune':
        return _run_prune(options, out, err)
    return _run_status(options, out, err)


def main(argv=None):
    """ The command line entry point. """
    return run(build_parser().parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())

#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
""" Replay the MQTT messages the message tracker recorded.

    The tracker records what paho saw, which is not the same as what the broker
    received. When that leaves a message 'failed' or 'unconfirmed', an operator
    can replay it with this tool.

    A replay is a new row in the tracker table that points at the original with
    'origin_id' and 'attempt'. The original row is never changed.

    The tool is a dry run unless --publish is given.
"""

# pylint: disable=wrong-import-order
import argparse
import collections
import fnmatch
import os
import random
import sys
import threading
import time
import uuid

# When run as a script, the 'user' package is not on the path.
_bin_root = os.getenv('BIN_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _bin_root not in sys.path:
    sys.path.append(_bin_root)

import weedb  # pylint: disable=wrong-import-position
from weeutil.weeutil import to_bool  # pylint: disable=wrong-import-position

import user.mqttcommon  # pylint: disable=wrong-import-position
import user.mqttpublish  # pylint: disable=wrong-import-position
import user.mqttmessagetracker  # pylint: disable=wrong-import-position

VERSION = user.mqttpublish.VERSION

# The tracker table's columns and plugin section are shared with the tracker and mqttprune.
MESSAGE_COLUMNS = user.mqttmessagetracker.MESSAGE_COLUMNS

# A 'sent' row may still be in flight and an 'acked' row does not need a replay.
REPLAY_STATUSES = (user.mqttmessagetracker.STATUS_UNCONFIRMED,
                   user.mqttmessagetracker.STATUS_FAILED)

DEFAULT_STATUS = user.mqttmessagetracker.STATUS_UNCONFIRMED
DEFAULT_PLUGIN_SECTION = user.mqttmessagetracker.DEFAULT_PLUGIN_SECTION
DEFAULT_SINCE = 3600
DEFAULT_LIMIT = 100
DEFAULT_ACK_TIMEOUT = 10
DEFAULT_CONNECT_TIMEOUT = 10

# What paho returns when it accepted the publish.
_RC_SUCCESS = 0

ReplayOutcome = collections.namedtuple('ReplayOutcome', 'row attempt mid status')


class ReplayError(Exception):
    """ A replay failure. """


class ReplayConfigError(ReplayError):
    """ A configuration or database problem. """


class ReplayConnectError(ReplayError):
    """ The tool could not connect to the broker, nothing was published. """


def read_config(config_file):
    """ Read the WeeWX config file. """
    try:
        return user.mqttmessagetracker.read_config(config_file)
    except user.mqttmessagetracker.TrackerConfigError as exception:
        raise ReplayConfigError(str(exception)) from exception


def replay_config(config_dict, plugin_section=DEFAULT_PLUGIN_SECTION, data_binding=None, table=None,
                  clientid=None):
    """ Resolve the database, table and mqtt connection options for a replay. """
    try:
        _, database_dict, table_name = user.mqttmessagetracker.tool_config(
            config_dict, plugin_section, data_binding, table)
    except user.mqttmessagetracker.TrackerConfigError as exception:
        raise ReplayConfigError(str(exception)) from exception

    service_dict = dict(config_dict.get('MQTTPublish', {}))
    # Never reuse the service's clientid, the broker would disconnect the running service.
    service_dict.pop('clientid', None)
    if clientid:
        service_dict['clientid'] = clientid
    options = user.mqttpublish.mqtt_connection_options(
        service_dict, default_clientid=f'MQTTPublish-replay-{random.randint(1000, 9999)}')  # NOSONAR - just need a unique id
    return database_dict, table_name, options


def _origin(row):
    """ The id of the original message a row belongs to. """
    return row['origin_id'] or row['id']


def _may_be_on_the_broker(row):
    """ A failed publish is the only row that is certainly not on the broker. """
    return row['status'] != user.mqttmessagetracker.STATUS_FAILED


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _candidate(row, statuses, oldest, topic, acked_origins, force):
    """ Whether a row passes the filters that do not depend on the other rows. """
    if row['status'] not in statuses:
        return False
    if oldest is not None and row['sent_ts'] < oldest:
        return False
    if topic and not fnmatch.fnmatchcase(row['topic'], topic):
        return False
    if not force and _origin(row) in acked_origins:
        return False
    return True


def _newest_per_topic(rows):
    """ When each topic was last written, ignoring the rows certainly not on the broker. """
    newest = {}
    for row in rows:
        if _may_be_on_the_broker(row):
            newest[row['topic']] = max(newest.get(row['topic'], row['sent_ts']), row['sent_ts'])
    return newest


def _is_acked_replay(row):
    """ Whether the row is a replay that paho reported as published. """
    return row['origin_id'] is not None and row['status'] == user.mqttmessagetracker.STATUS_ACKED


def _acked_origins(rows):
    """ The origin ids that already have an acked replay. """
    return {row['origin_id'] for row in rows if _is_acked_replay(row)}


def _oldest(since, now):
    """ The oldest sent_ts to consider, None when every row is considered. """
    if since is None or since <= 0:
        return None
    return now - since


def _sort_key(row):
    """ The publish order of the selected rows. """
    return row['sent_ts'], row['id']


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _select(rows, statuses, oldest, topic, acked_origins, force, newest, newest_per_topic):
    """ The rows that pass the filters, in publish order. """
    selected = []
    for row in rows:
        if not _candidate(row, statuses, oldest, topic, acked_origins, force):
            continue
        if newest_per_topic and row['sent_ts'] < newest.get(row['topic'], row['sent_ts']):
            continue
        selected.append(row)
    return selected


def _limit(rows, limit):
    """ Keep the newest rows, then return them in publish order. """
    if limit is None or limit <= 0:
        return rows
    newest = sorted(rows, key=_sort_key, reverse=True)[:limit]
    return sorted(newest, key=_sort_key)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def select_messages(rows, statuses=None, since=DEFAULT_SINCE, limit=DEFAULT_LIMIT, topic=None,
                    newest_per_topic=True, force=False, now=None):
    """ Select the rows to replay.

        Only the newest row per topic is selected by default, so replayed
        values cannot overwrite newer ones. A message that already has an
        acked replay is skipped unless 'force' is set. """
    statuses = tuple(statuses or (DEFAULT_STATUS,))
    now = time.time() if now is None else now

    selected = _select(rows, statuses, _oldest(since, now), topic, _acked_origins(rows), force,
                       _newest_per_topic(rows) if newest_per_topic else {}, newest_per_topic)
    return _limit(selected, limit)


def decode_payload(row):
    """ Reconstruct the payload from its stored value and encoding. """
    payload = row['payload']
    if payload is None:
        return None
    if row['payload_encoding'] == 'hex':
        return bytes.fromhex(payload)
    return payload


def next_attempt(cursor, table, origin_id):
    """ The attempt number for the next replay of an original message. """
    cursor.execute(f"SELECT attempt FROM {table} WHERE origin_id = ?", (origin_id,))
    attempts = [row[0] for row in cursor if row[0] is not None]
    return max(attempts, default=0) + 1


# pylint: disable=too-many-arguments,too-many-positional-arguments
def insert_attempt(connection, table, row, mid, rc, sent_ts, clientid):
    """ Insert the row of a replay, returning its id, attempt and status. """
    origin_id = _origin(row)
    status = user.mqttmessagetracker.STATUS_FAILED
    if rc == _RC_SUCCESS:
        status = user.mqttmessagetracker.STATUS_SENT
    row_id = uuid.uuid4().hex
    with weedb.Transaction(connection) as cursor:
        attempt = next_attempt(cursor, table, origin_id)
        cursor.execute(
            f"INSERT INTO {table} "
            "(id, mid, dateTime, sent_ts, arrived_ts, status, unconfirmed_ts, "
            "origin_id, attempt, clientid, topic, qos, retain, rc, payload, payload_encoding) "
            "VALUES (?, ?, ?, ?, NULL, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row_id, mid, row['dateTime'], sent_ts, status, origin_id, attempt, clientid,
             row['topic'], row['qos'], row['retain'], rc, row['payload'], row['payload_encoding']))
    return row_id, attempt, status


def update_attempt(connection, table, row_id, status, timestamp=None):
    """ Record the outcome of a replay. """
    timestamp = time.time() if timestamp is None else timestamp
    if status == user.mqttmessagetracker.STATUS_ACKED:
        statement = f"UPDATE {table} SET status = ?, arrived_ts = ? WHERE id = ?"
    else:
        statement = f"UPDATE {table} SET status = ?, unconfirmed_ts = ? WHERE id = ?"
    with weedb.Transaction(connection) as cursor:
        cursor.execute(statement, (status, timestamp, row_id))


class ReplayClient:  # pylint: disable=too-many-instance-attributes
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
            raise ReplayConnectError(
                f"Unable to connect to {self.options['host']}:{self.options['port']}: "
                f"{exception}") from exception

        self.client.loop_start()
        if not self.connected.wait(self.connect_timeout):
            self._close()
            raise ReplayConnectError(
                f"No CONNACK from {self.options['host']}:{self.options['port']} within "
                f"{self.connect_timeout} seconds.")
        if self.connect_rc != _RC_SUCCESS:
            self._close()
            raise ReplayConnectError(f"The broker refused the connection, rc {self.connect_rc}.")

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


def replay_message(client, connection, table, row, clientid):
    """ Publish one message and record its outcome. """
    try:
        payload = decode_payload(row)
    except ValueError as exception:
        raise ReplayConfigError(
            f"Unable to decode the payload of {row['id']}: {exception}") from exception

    message_info = client.publish(row['topic'], payload, row['qos'], row['retain'])
    row_id, attempt, status = insert_attempt(
        connection, table, row, message_info.mid, int(message_info.rc), time.time(), clientid)

    if status == user.mqttmessagetracker.STATUS_FAILED:
        return ReplayOutcome(row, attempt, message_info.mid, status)

    arrived_ts = client.wait_for_ack(message_info.mid)
    if arrived_ts is None:
        status = user.mqttmessagetracker.STATUS_UNCONFIRMED
        update_attempt(connection, table, row_id, status)
    else:
        status = user.mqttmessagetracker.STATUS_ACKED
        update_attempt(connection, table, row_id, status, arrived_ts)
    return ReplayOutcome(row, attempt, message_info.mid, status)


def print_outcomes(outcomes, out):
    """ Print what the broker acknowledged. """
    for outcome in outcomes:
        print(f"  {outcome.status:<12} {outcome.row['topic']} attempt={outcome.attempt} "
              f"mid={outcome.mid}", file=out)


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
def replay(database_dict, table, options, *, statuses=None, since=DEFAULT_SINCE,
           limit=DEFAULT_LIMIT, topic=None, newest_per_topic=True, force=False, dry_run=True,
           ack_timeout=DEFAULT_ACK_TIMEOUT, connect_timeout=DEFAULT_CONNECT_TIMEOUT, out=None):
    """ Replay the selected messages, returning the selection and the outcomes.

        Nothing is published when 'dry_run' is set, or when nothing is selected. """
    out = sys.stdout if out is None else out
    try:
        connection = weedb.connect(database_dict)
    except weedb.DatabaseError as exception:
        raise ReplayConfigError(
            f"Unable to open the message tracker database: {exception}") from exception

    try:
        rows = user.mqttmessagetracker.fetch_rows(connection, table)
        selected = select_messages(rows, statuses=statuses, since=since, limit=limit, topic=topic,
                                   newest_per_topic=newest_per_topic, force=force)
        user.mqttmessagetracker.print_plan(selected, out)
        if dry_run or not selected:
            return selected, []

        client = ReplayClient(options, ack_timeout=ack_timeout, connect_timeout=connect_timeout)
        client.connect()
        try:
            outcomes = [replay_message(client, connection, table, row, options['clientid'])
                        for row in selected]
        finally:
            client.close()
    except weedb.DatabaseError as exception:
        raise ReplayConfigError(
            f"Unable to use the message tracker table {table}: {exception}") from exception
    finally:
        connection.close()

    print_outcomes(outcomes, out)
    return selected, outcomes


def _statuses(value):
    """ Parse the statuses a message can be replayed from. """
    statuses = [status.strip() for status in value.split(',') if status.strip()]
    invalid = [status for status in statuses if status not in REPLAY_STATUSES]
    if invalid:
        raise argparse.ArgumentTypeError(
            f"invalid status(es) {', '.join(invalid)}, choose from {', '.join(REPLAY_STATUSES)}")
    return statuses


def build_parser():
    """ The command line options. """
    parser = argparse.ArgumentParser(
        description="Replay the MQTT messages the message tracker recorded.",
        epilog="Without --publish the selection is only printed, nothing is sent.")
    parser.add_argument('config_file', help="The WeeWX config file, for example /etc/weewx/weewx.conf.")
    parser.add_argument('--version', action='version', version=f'%(prog)s {VERSION}')

    parser.add_argument('--plugin-section', default=DEFAULT_PLUGIN_SECTION,
                        help=(f"The config section of the tracker plugin. "
                              f"Default is {DEFAULT_PLUGIN_SECTION}."))
    parser.add_argument('--data-binding', default=None,
                        help="Override the tracker's data_binding option.")
    parser.add_argument('--table', default=None,
                        help="Override the tracker's table option.")
    parser.add_argument('--clientid', default=None,
                        help="The clientid to connect with. Default is a unique MQTTPublish-replay id.")

    parser.add_argument('--status', type=_statuses, default=[DEFAULT_STATUS], metavar='STATUS',
                        help=(f"The statuses to replay, comma separated. "
                              f"Default is {DEFAULT_STATUS}. Choose from "
                              f"{', '.join(REPLAY_STATUSES)}."))
    parser.add_argument('--since', type=int, default=DEFAULT_SINCE, metavar='SECONDS',
                        help=f"Only replay messages sent within the last SECONDS. Default is {DEFAULT_SINCE}.")
    parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT, metavar='COUNT',
                        help=f"The maximum number of messages to replay. Default is {DEFAULT_LIMIT}.")
    parser.add_argument('--topic', default=None, metavar='GLOB',
                        help="Only replay topics that match the glob, for example 'weather/outTemp_*'.")
    parser.add_argument('--all', action='store_true',
                        help="Replay every selected message, not just the newest per topic.")
    parser.add_argument('--force', action='store_true',
                        help="Replay messages that already have an acked replay.")
    parser.add_argument('--publish', action='store_true',
                        help="Publish the selected messages. Without it nothing is sent.")

    parser.add_argument('--ack-timeout', type=float, default=DEFAULT_ACK_TIMEOUT, metavar='SECONDS',
                        help=f"How long to wait for each publish to be acknowledged. "
                             f"Default is {DEFAULT_ACK_TIMEOUT}.")
    parser.add_argument('--connect-timeout', type=float, default=DEFAULT_CONNECT_TIMEOUT, metavar='SECONDS',
                        help=f"How long to wait for the connection. Default is {DEFAULT_CONNECT_TIMEOUT}.")
    return parser


def run(options, out=None, err=None):
    """ Run the tool, returning the exit code. """
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    try:
        config_dict = read_config(options.config_file)
        database_dict, table, mqtt_options = replay_config(
            config_dict, options.plugin_section, options.data_binding, options.table, options.clientid)
        _, outcomes = replay(
            database_dict, table, mqtt_options, out=out,
            statuses=options.status, since=options.since, limit=options.limit, topic=options.topic,
            newest_per_topic=not options.all, force=options.force, dry_run=not options.publish,
            ack_timeout=options.ack_timeout, connect_timeout=options.connect_timeout)
    except ReplayConnectError as exception:
        print(f"mqttreplay: {exception}", file=err)
        return 1
    except ReplayConfigError as exception:
        print(f"mqttreplay: {exception}", file=err)
        return 2

    if not outcomes:
        return 0
    acked = all(outcome.status == user.mqttmessagetracker.STATUS_ACKED for outcome in outcomes)
    return 0 if acked else 1


def main(argv=None):
    """ The command line entry point. """
    return run(build_parser().parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())

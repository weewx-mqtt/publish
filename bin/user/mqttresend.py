#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
""" Resend the MQTT messages the message tracker recorded.

    The tracker records what paho saw, which is not the same as what the broker
    received. When that leaves a message 'failed' or 'unconfirmed', an operator
    can resend it with this tool.

    A resend is a new row in the tracker table that points at the original with
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

# The row helpers are shared with the tracker's automatic resend.
_origin = user.mqttmessagetracker.origin_id
decode_payload = user.mqttmessagetracker.decode_payload
next_attempt = user.mqttmessagetracker.next_attempt
insert_attempt = user.mqttmessagetracker.insert_attempt

# A 'sent' row may still be in flight and an 'confirmed' row does not need a resend.
RESEND_STATUSES = (user.mqttmessagetracker.STATUS_UNCONFIRMED,
                   user.mqttmessagetracker.STATUS_FAILED)

DEFAULT_STATUS = user.mqttmessagetracker.STATUS_UNCONFIRMED
DEFAULT_PLUGIN_SECTION = user.mqttmessagetracker.DEFAULT_PLUGIN_SECTION
# Every row is considered by default, so every unconfirmed message is resent.
DEFAULT_SINCE = None
DEFAULT_LIMIT = 100
DEFAULT_ACK_TIMEOUT = 10
DEFAULT_CONNECT_TIMEOUT = 10

# What paho returns when it accepted the publish.
_RC_SUCCESS = 0

ResendOutcome = collections.namedtuple('ResendOutcome', 'row attempt mid status')


class ResendError(Exception):
    """ A resend failure. """


class ResendConfigError(ResendError):
    """ A configuration or database problem. """


class ResendConnectError(ResendError):
    """ The tool could not connect to the broker, nothing was published. """


def read_config(config_file):
    """ Read the WeeWX config file. """
    try:
        return user.mqttmessagetracker.read_config(config_file)
    except user.mqttmessagetracker.TrackerConfigError as exception:
        raise ResendConfigError(str(exception)) from exception


def resend_config(config_dict, plugin_section=DEFAULT_PLUGIN_SECTION, data_binding=None, table=None,
                  clientid=None):
    """ Resolve the database, table and mqtt connection options for a resend. """
    try:
        _, database_dict, table_name = user.mqttmessagetracker.tool_config(
            config_dict, plugin_section, data_binding, table)
    except user.mqttmessagetracker.TrackerConfigError as exception:
        raise ResendConfigError(str(exception)) from exception

    service_dict = dict(config_dict.get('MQTTPublish', {}))
    # Never reuse the service's clientid, the broker would disconnect the running service.
    service_dict.pop('clientid', None)
    if clientid:
        service_dict['clientid'] = clientid
    options = user.mqttpublish.mqtt_connection_options(
        service_dict, default_clientid=f'MQTTPublish-resend-{random.randint(1000, 9999)}')  # NOSONAR - just need a unique id
    return database_dict, table_name, options


def _may_be_on_the_broker(row):
    """ A failed publish is the only row that is certainly not on the broker. """
    return row['status'] != user.mqttmessagetracker.STATUS_FAILED


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _candidate(row, statuses, oldest, topic, confirmed_origins, force):
    """ Whether a row passes the filters that do not depend on the other rows. """
    if row['status'] not in statuses:
        return False
    if oldest is not None and row['sent_ts'] < oldest:
        return False
    if topic and not fnmatch.fnmatchcase(row['topic'], topic):
        return False
    if not force and _origin(row) in confirmed_origins:
        return False
    return True


def _newest_per_topic(rows):
    """ When each topic was last written, ignoring the rows certainly not on the broker. """
    newest = {}
    for row in rows:
        if _may_be_on_the_broker(row):
            newest[row['topic']] = max(newest.get(row['topic'], row['sent_ts']), row['sent_ts'])
    return newest


def _is_confirmed_resend(row):
    """ Whether the row is a resend that paho reported as published. """
    return row['origin_id'] is not None and row['status'] == user.mqttmessagetracker.STATUS_CONFIRMED


def _confirmed_origins(rows):
    """ The origin ids that already have a confirmed resend. """
    return {row['origin_id'] for row in rows if _is_confirmed_resend(row)}


def _oldest(since, now):
    """ The oldest sent_ts to consider, None when every row is considered. """
    if since is None or since <= 0:
        return None
    return now - since


def _sort_key(row):
    """ The publish order of the selected rows. """
    return row['sent_ts'], row['id']


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _candidates(rows, statuses, since, topic, force, now):
    """ The rows that pass the filters that do not depend on the other rows. """
    statuses = tuple(statuses or (DEFAULT_STATUS,))
    oldest = _oldest(since, now)
    confirmed_origins = _confirmed_origins(rows)
    return [row for row in rows
            if _candidate(row, statuses, oldest, topic, confirmed_origins, force)]


def _is_stale(row, newest):
    """ Whether a newer message was published on the row's topic. """
    return row['sent_ts'] < newest.get(row['topic'], row['sent_ts'])


def _select(candidates, newest):
    """ The candidates that a newer message on the same topic does not make stale.

        'newest' is empty when every candidate is kept. """
    return [row for row in candidates if not _is_stale(row, newest)]


def _limit(rows, limit):
    """ Keep the newest rows, then return them in publish order. """
    if limit is None or limit <= 0:
        return rows
    newest = sorted(rows, key=_sort_key, reverse=True)[:limit]
    return sorted(newest, key=_sort_key)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def select_messages(rows, statuses=None, since=DEFAULT_SINCE, limit=DEFAULT_LIMIT, topic=None,
                    newest_per_topic=True, force=False, now=None):
    """ Select the rows to resend.

        Every row is considered unless 'since' bounds its age. Only the newest row per topic
        is selected by default, so resent values cannot overwrite newer ones. A message that
        already has a confirmed resend is skipped unless 'force' is set. """
    candidates = _candidates(rows, statuses, since, topic, force, time.time() if now is None else now)
    newest = _newest_per_topic(rows) if newest_per_topic else {}
    return _limit(_select(candidates, newest), limit)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def superseded(rows, statuses=None, since=DEFAULT_SINCE, topic=None, force=False, now=None):
    """ The rows a resend would keep, but for a newer message on the same topic.

        Resending one would write an older value over a newer one, so they are only selected
        with '--all'. """
    newest = _newest_per_topic(rows)
    return [row for row in _candidates(rows, statuses, since, topic, force, time.time() if now is None else now)
            if _is_stale(row, newest)]


def update_attempt(connection, table, row_id, status, timestamp=None):
    """ Record the outcome of a resend. """
    timestamp = time.time() if timestamp is None else timestamp
    if status == user.mqttmessagetracker.STATUS_CONFIRMED:
        statement = f"UPDATE {table} SET status = ?, arrived_ts = ? WHERE id = ?"
    else:
        statement = f"UPDATE {table} SET status = ?, unconfirmed_ts = ? WHERE id = ?"
    with weedb.Transaction(connection) as cursor:
        cursor.execute(statement, (status, timestamp, row_id))


class ResendClient:  # pylint: disable=too-many-instance-attributes
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
            raise ResendConnectError(
                f"Unable to connect to {self.options['host']}:{self.options['port']}: "
                f"{exception}") from exception

        self.client.loop_start()
        if not self.connected.wait(self.connect_timeout):
            self._close()
            raise ResendConnectError(
                f"No CONNACK from {self.options['host']}:{self.options['port']} within "
                f"{self.connect_timeout} seconds.")
        if self.connect_rc != _RC_SUCCESS:
            self._close()
            raise ResendConnectError(f"The broker refused the connection, rc {self.connect_rc}.")

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


def resend_message(client, connection, table, row, clientid):
    """ Publish one message and record its outcome. """
    try:
        payload = decode_payload(row)
    except ValueError as exception:
        raise ResendConfigError(
            f"Unable to decode the payload of {row['id']}: {exception}") from exception

    message_info = client.publish(row['topic'], payload, row['qos'], row['retain'])
    row_id, attempt, status = insert_attempt(
        connection, table, row, message_info.mid, int(message_info.rc), time.time(), clientid)

    if status == user.mqttmessagetracker.STATUS_FAILED:
        return ResendOutcome(row, attempt, message_info.mid, status)

    arrived_ts = client.wait_for_ack(message_info.mid)
    if arrived_ts is None:
        status = user.mqttmessagetracker.STATUS_UNCONFIRMED
        update_attempt(connection, table, row_id, status)
    else:
        status = user.mqttmessagetracker.STATUS_CONFIRMED
        update_attempt(connection, table, row_id, status, arrived_ts)
    return ResendOutcome(row, attempt, message_info.mid, status)


def print_outcomes(outcomes, out):
    """ Print what the broker acknowledged. """
    for outcome in outcomes:
        print(f"  {outcome.status:<12} {outcome.row['topic']} attempt={outcome.attempt} "
              f"mid={outcome.mid}", file=out)


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
def resend(database_dict, table, options, *, statuses=None, since=DEFAULT_SINCE,
           limit=DEFAULT_LIMIT, topic=None, newest_per_topic=True, force=False, dry_run=True,
           ack_timeout=DEFAULT_ACK_TIMEOUT, connect_timeout=DEFAULT_CONNECT_TIMEOUT, out=None):
    """ Resend the selected messages, returning the selection and the outcomes.

        Nothing is published when 'dry_run' is set, or when nothing is selected. """
    out = sys.stdout if out is None else out
    try:
        connection = weedb.connect(database_dict)
    except weedb.DatabaseError as exception:
        raise ResendConfigError(
            f"Unable to open the message tracker database: {exception}") from exception

    try:
        rows = user.mqttmessagetracker.fetch_rows(connection, table)
        selected = select_messages(rows, statuses=statuses, since=since, limit=limit, topic=topic,
                                   newest_per_topic=newest_per_topic, force=force)
        user.mqttmessagetracker.print_plan(selected, out)
        if newest_per_topic:
            stale = superseded(rows, statuses=statuses, since=since, topic=topic, force=force)
            if stale:
                print(f"{len(stale)} message(s) are older than a newer message on their topic, "
                      "use --all to resend them.", file=out)
        if dry_run or not selected:
            return selected, []

        client = ResendClient(options, ack_timeout=ack_timeout, connect_timeout=connect_timeout)
        client.connect()
        try:
            outcomes = [resend_message(client, connection, table, row, options['clientid'])
                        for row in selected]
        finally:
            client.close()
    except weedb.DatabaseError as exception:
        raise ResendConfigError(
            f"Unable to use the message tracker table {table}: {exception}") from exception
    finally:
        connection.close()

    print_outcomes(outcomes, out)
    return selected, outcomes


def _statuses(value):
    """ Parse the statuses a message can be resent from. """
    statuses = [status.strip() for status in value.split(',') if status.strip()]
    invalid = [status for status in statuses if status not in RESEND_STATUSES]
    if invalid:
        raise argparse.ArgumentTypeError(
            f"invalid status(es) {', '.join(invalid)}, choose from {', '.join(RESEND_STATUSES)}")
    return statuses


def build_parser():
    """ The command line options. """
    parser = argparse.ArgumentParser(
        description="Resend the MQTT messages the message tracker recorded.",
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
                        help="The clientid to connect with. Default is a unique MQTTPublish-resend id.")

    parser.add_argument('--status', type=_statuses, default=[DEFAULT_STATUS], metavar='STATUS',
                        help=(f"The statuses to resend, comma separated. "
                              f"Default is {DEFAULT_STATUS}. Choose from "
                              f"{', '.join(RESEND_STATUSES)}."))
    parser.add_argument('--since', type=int, default=DEFAULT_SINCE, metavar='SECONDS',
                        help="Only resend messages sent within the last SECONDS. "
                             "Default is every message.")
    parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT, metavar='COUNT',
                        help=f"The maximum number of messages to resend. Default is {DEFAULT_LIMIT}.")
    parser.add_argument('--topic', default=None, metavar='GLOB',
                        help="Only resend topics that match the glob, for example 'weather/outTemp_*'.")
    parser.add_argument('--all', action='store_true',
                        help="Resend every selected message, not just the newest per topic.")
    parser.add_argument('--force', action='store_true',
                        help="Resend messages that already have a confirmed resend.")
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
        database_dict, table, mqtt_options = resend_config(
            config_dict, options.plugin_section, options.data_binding, options.table, options.clientid)
        _, outcomes = resend(
            database_dict, table, mqtt_options, out=out,
            statuses=options.status, since=options.since, limit=options.limit, topic=options.topic,
            newest_per_topic=not options.all, force=options.force, dry_run=not options.publish,
            ack_timeout=options.ack_timeout, connect_timeout=options.connect_timeout)
    except ResendConnectError as exception:
        print(f"mqttresend: {exception}", file=err)
        return 1
    except ResendConfigError as exception:
        print(f"mqttresend: {exception}", file=err)
        return 2

    if not outcomes:
        return 0
    confirmed = all(outcome.status == user.mqttmessagetracker.STATUS_CONFIRMED for outcome in outcomes)
    return 0 if confirmed else 1


def main(argv=None):
    """ The command line entry point. """
    return run(build_parser().parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())

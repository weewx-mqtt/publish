#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
""" Track published MQTT messages in the WeeWX database. """

# pylint: disable=wrong-import-order
import os
import queue
import re
import threading
import time
import uuid

import configobj
import paho.mqtt.client as mqtt
import weecfg
import weewx
import weewx.manager
import weedb
from weeutil.weeutil import to_bool, to_int

import user.mqttpublish
import user.mqttcommon


TABLE_NAME_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
DEFAULT_TABLE = 'mqtt_message_tracker'
DEFAULT_PLUGIN_SECTION = 'MQTTMessageTracker'
DEFAULT_RETENTION = 604800
DEFAULT_UNCONFIRMED_RETENTION = 0

# The payload preview length in a tool's plan.
PREVIEW_LENGTH = 60

# The columns read from the tracker table, in the order they are fetched.
# weedb's MySQL cursor has no 'description' and no 'rowcount', so the names are fixed here.
MESSAGE_COLUMNS = ('id', 'mid', 'dateTime', 'sent_ts', 'arrived_ts', 'status', 'unconfirmed_ts',
                   'origin_id', 'attempt', 'clientid', 'topic', 'qos', 'retain', 'rc',
                   'payload', 'payload_encoding')


class TrackerConfigError(Exception):
    """ A tracker option that prevents writing to the database. """


def read_config(config_file):
    """ Read the WeeWX config file, as WeeWX reads it.

        weecfg supplies WEEWX_ROOT, which the database bindings need to resolve
        an SQLITE_ROOT in [DatabaseTypes]. """
    try:
        _config_path, config_dict = weecfg.read_config(os.path.abspath(config_file))
        return config_dict
    except (OSError, SyntaxError, configobj.ConfigObjError) as exception:
        raise TrackerConfigError(f"Unable to read the config file {config_file}: {exception}.") from exception


def tool_config(config_dict, plugin_section=DEFAULT_PLUGIN_SECTION, data_binding=None, table=None):
    """ Resolve the plugin section, database and table a tool works with. """
    if plugin_section not in config_dict:
        raise TrackerConfigError(f"The config file has no [{plugin_section}] section.")

    plugin_dict = dict(config_dict[plugin_section])
    if data_binding:
        plugin_dict['data_binding'] = data_binding
    if table:
        plugin_dict['table'] = table

    database_dict, table_name = resolve_tracker_config(plugin_dict, config_dict)
    return plugin_dict, database_dict, table_name


def resolve_tracker_config(plugin_dict, config_dict):
    """ Resolve the database and table a tracker writes to.

        Raises TrackerConfigError when the options cannot be used. """
    data_binding = plugin_dict.get('data_binding')
    if not data_binding:
        raise TrackerConfigError("The data_binding option is required and must name a separate database binding.")

    try:
        manager_dict = weewx.manager.get_manager_dict_from_config(config_dict, data_binding)
    except (KeyError, TypeError, weewx.UnknownBinding) as exception:
        raise TrackerConfigError(f"Unable to resolve data binding {data_binding}: {exception}.") from exception

    table = plugin_dict.get('table', DEFAULT_TABLE)
    if not isinstance(table, str) or not TABLE_NAME_PATTERN.match(table):
        raise TrackerConfigError(f"Invalid table name, {table}.")

    return manager_dict['database_dict'], table


def _topic_option(topic_dicts, key, default):
    """ One option, per enabled topic, from a [[topics]] section. """
    values = {}
    for topic in topic_dicts.sections:
        topic_dict = topic_dicts[topic]
        if not to_bool(topic_dict.get('enable', True)):
            continue
        value = to_int(topic_dict.get(key, default))
        values[topic] = default if value is None else value
    return values


def topic_retentions(topic_dicts, default_retention):
    """ The retention for each enabled topic in a [[topics]] section. """
    return _topic_option(topic_dicts, 'retention', default_retention)


def topic_unconfirmed_retentions(topic_dicts, default_retention):
    """ The unconfirmed retention for each enabled topic in a [[topics]] section. """
    return _topic_option(topic_dicts, 'unconfirmed_retention', default_retention)


def fetch_rows(connection, table):
    """ Read every row from the tracker table. """
    cursor = connection.cursor()
    try:
        cursor.execute(f"SELECT {', '.join(MESSAGE_COLUMNS)} FROM {table}")
        return [dict(zip(MESSAGE_COLUMNS, row)) for row in cursor]
    finally:
        cursor.close()


def describe_row(row):
    """ A one line description of a row for a tool's plan. """
    payload = row['payload']
    if payload is None:
        preview = '<none>'
    else:
        preview = payload[:PREVIEW_LENGTH] + ('...' if len(payload) > PREVIEW_LENGTH else '')
        preview = preview.replace('\n', ' ')
    return (f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(row['sent_ts']))} "
            f"{row['topic']} qos={row['qos']} retain={row['retain']} "
            f"status={row['status']} id={row['id']} payload={preview}")


def print_plan(rows, out):
    """ Print the rows a tool selected. """
    if not rows:
        print("No messages match the selection.", file=out)
        return
    print(f"{len(rows)} message(s) selected:", file=out)
    for row in rows:
        print(f"  {describe_row(row)}", file=out)

# The column types work with both SQLite and MySQL.
# MEDIUMTEXT is MySQL's 16 MB text type; SQLite accepts the name and gives it TEXT affinity.
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS {table} (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    mid INTEGER NOT NULL,
    dateTime INTEGER,
    sent_ts DOUBLE NOT NULL,
    arrived_ts DOUBLE,
    status VARCHAR(16) NOT NULL,
    unconfirmed_ts DOUBLE,
    origin_id VARCHAR(32),
    attempt INTEGER,
    clientid VARCHAR(128),
    topic VARCHAR(512) NOT NULL,
    qos INTEGER NOT NULL,
    retain INTEGER NOT NULL,
    rc INTEGER,
    payload MEDIUMTEXT,
    payload_encoding VARCHAR(8)
)
"""

# The rc paho returns when it accepted the publish.
_RC_SUCCESS = 0

# The event tags.
_EVENT_SENT = 'sent'
_EVENT_ARRIVED = 'arrived'
_EVENT_FINALIZE = 'finalize'
_EVENT_DISCONNECT = 'disconnect'
_EVENT_RESEND = 'resend'
_CONTROL_EVENTS = (_EVENT_FINALIZE, _EVENT_DISCONNECT, _EVENT_RESEND)

# The values of the status column.
STATUS_FAILED = 'failed'
STATUS_SENT = 'sent'
STATUS_CONFIRMED = 'confirmed'
STATUS_UNCONFIRMED = 'unconfirmed'

# The statuses whose rows are pruned by age. A row that may still be delivered, or whose
# delivery is unknown, is kept so that it can still be resent.
_PRUNED_STATUSES = (STATUS_CONFIRMED, STATUS_FAILED)


def origin_id(row):
    """ The id of the original message a row belongs to. """
    return row['origin_id'] or row['id']


def decode_payload(row):
    """ Reconstruct the payload from its stored value and encoding. """
    payload = row['payload']
    if payload is None:
        return None
    if row['payload_encoding'] == 'hex':
        return bytes.fromhex(payload)
    return payload


def next_attempt(cursor, table, row_origin_id):
    """ The attempt number for the next resend of an original message. """
    cursor.execute(f"SELECT attempt FROM {table} WHERE origin_id = ?", (row_origin_id,))
    attempts = [row[0] for row in cursor if row[0] is not None]
    return max(attempts, default=0) + 1


# pylint: disable=too-many-arguments,too-many-positional-arguments
def insert_attempt(connection, table, row, mid, rc, sent_ts, clientid):
    """ Insert the row of a resend, returning its id, attempt and status. """
    row_origin_id = origin_id(row)
    status = STATUS_FAILED
    if rc == _RC_SUCCESS:
        status = STATUS_SENT
    row_id = uuid.uuid4().hex
    with weedb.Transaction(connection) as cursor:
        attempt = next_attempt(cursor, table, row_origin_id)
        cursor.execute(
            f"INSERT INTO {table} "
            "(id, mid, dateTime, sent_ts, arrived_ts, status, unconfirmed_ts, "
            "origin_id, attempt, clientid, topic, qos, retain, rc, payload, payload_encoding) "
            "VALUES (?, ?, ?, ?, NULL, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row_id, mid, row['dateTime'], sent_ts, status, row_origin_id, attempt, clientid,
             row['topic'], row['qos'], row['retain'], rc, row['payload'], row['payload_encoding']))
    return row_id, attempt, status


def _confirmed_origins(rows):
    """ The origin ids that already have a confirmed resend. """
    return {row['origin_id'] for row in rows
            if row['origin_id'] is not None and row['status'] == STATUS_CONFIRMED}


def _last_success(rows, confirmed_origins):
    """ The newest confirmed original publish time for each topic. """
    last_success = {}
    for row in rows:
        if row['origin_id'] is not None:
            continue
        if row['status'] != STATUS_CONFIRMED and row['id'] not in confirmed_origins:
            continue
        last_success[row['topic']] = max(last_success.get(row['topic'], row['sent_ts']), row['sent_ts'])
    return last_success


def _after_last_success(row, oldest, last_success, confirmed_origins):
    """ Whether a row is a failed/unconfirmed message after its topic's last success. """
    if row['status'] not in (STATUS_UNCONFIRMED, STATUS_FAILED):
        return False
    if oldest is not None and row['sent_ts'] < oldest:
        return False
    boundary = last_success.get(row['topic'])
    if boundary is not None and row['sent_ts'] <= boundary:
        return False
    return origin_id(row) not in confirmed_origins


def _dedupe(rows):
    """ Keep the earliest row for each original message. """
    # A message may have several resend attempts. Resend the original once, not each attempt;
    # the earliest row is the original, or the oldest attempt when the original was pruned.
    seen = set()
    unique = []
    for row in sorted(rows, key=lambda item: (item['sent_ts'], item['id'])):
        row_origin_id = origin_id(row)
        if row_origin_id in seen:
            continue
        seen.add(row_origin_id)
        unique.append(row)
    return unique


def select_after_last_success(rows, since=None, now=None, include_before_last_success=False):
    """ Select the unconfirmed and failed rows to resend.

        By default only rows after the last confirmed publish on their topic are selected.
        The boundary is the newest confirmed original row on each topic. An original counts as
        confirmed when its own status is confirmed, or when it has a confirmed resend. A resend's
        own sent_ts does not move the boundary: a successful resend would otherwise hide an older
        backlog.

        With include_before_last_success, every unconfirmed and failed row is a candidate,
        including rows older than the topic's last confirmed publish. """
    now = time.time() if now is None else now
    oldest = None if since is None or since <= 0 else now - since
    confirmed_origins = _confirmed_origins(rows)
    last_success = {} if include_before_last_success else _last_success(rows, confirmed_origins)
    selected = [row for row in rows
                if _after_last_success(row, oldest, last_success, confirmed_origins)]
    return _dedupe(selected)


class _TrackerThread(threading.Thread):  # pylint: disable=too-many-instance-attributes
    """ Write publish events to the database on a single thread. """

    def __init__(self, logger_queue, log_name, database_dict, table,  # pylint: disable=too-many-arguments,too-many-positional-arguments
                 retention, topic_retention, unconfirmed_retention, topic_unconfirmed_retention,
                 prune_interval, batch_size, pending_ttl, queue_size, shutdown_timeout,
                 create_database):
        threading.Thread.__init__(self)
        self.daemon = True

        self.logger_queue = logger_queue
        self.log_name = log_name
        self.database_dict = database_dict
        self.table = table
        self.retention = retention
        self.topic_retention = topic_retention
        self.unconfirmed_retention = unconfirmed_retention
        self.topic_unconfirmed_retention = topic_unconfirmed_retention
        self.prune_interval = prune_interval
        self.batch_size = batch_size
        self.pending_ttl = pending_ttl
        self.shutdown_timeout = shutdown_timeout
        self.create_database = create_database

        self.queue = queue.Queue(maxsize=queue_size)
        self.accepting = True
        self.shutting_down = False
        self.dropped = 0
        # mid -> (row id, sent timestamp) for the messages paho has not confirmed.
        self.inflight = {}
        self.pending = {}

    def sent(self, mid, rc, topic, payload, qos, retain, date_time):  # pylint: disable=too-many-arguments,too-many-positional-arguments
        """ Queue a message that was handed to paho. """
        payload_text, payload_encoding = self._payload(payload)
        self._put((_EVENT_SENT, uuid.uuid4().hex, mid, rc, topic, payload_text, payload_encoding,
                   qos, int(retain), date_time, time.time()))

    def arrived(self, mid):
        """ Queue a message that paho reported as published. """
        self._put((_EVENT_ARRIVED, mid, time.time()))

    def disconnected(self, timestamp):
        """ Queue an event that marks the messages in flight as unconfirmed. """
        self._put((_EVENT_DISCONNECT, timestamp))

    def resend(self, client, options, clientid):
        """ Queue a resend for the messages after the last confirmed publish. """
        self._put((_EVENT_RESEND, client, options, clientid))

    def shutdown(self):
        """ Stop the thread after it has written the queued events and marked the unreported ones. """
        if not self.is_alive():
            return
        self.shutting_down = True
        self._log('INFO', "Shutting down.")
        try:
            self.queue.put((_EVENT_FINALIZE, time.time()), timeout=self.shutdown_timeout)
        except queue.Full:
            self._log('ERROR', "Unable to queue the message tracker shutdown event.")
            return
        self.join(self.shutdown_timeout)
        if self.is_alive():
            self._log('ERROR', f"Message tracker did not shut down within {self.shutdown_timeout} seconds.")

    def run(self):
        """ Write the queued events until the shutdown event arrives. """
        threading.current_thread().name = f"{self.log_name}-{threading.get_native_id()}"

        connection = None
        try:
            connection = self._connect()
            connection.execute(CREATE_TABLE.format(table=self.table))
            self._sweep(connection)
        except Exception as exception:  # pylint: disable=broad-exception-caught
            self.accepting = False
            self._log('ERROR', f"Unable to open the message tracker database: {exception}.")
            self._drain()
            if connection is not None:
                connection.close()
            return

        self._log('INFO', f"Tracking MQTT messages in table {self.table}.")

        try:
            self._run(connection)
        finally:
            self.accepting = False
            connection.close()
            self._log('INFO', "Message tracker is shut down.")

    def _connect(self):
        """ Open the database, creating it when configured to do so. """
        try:
            return weedb.connect(self.database_dict)
        except weedb.NoDatabaseError:
            if not self.create_database:
                raise
            self._log('INFO', f"Creating the message tracker database {self.database_dict.get('database_name')}.")
            try:
                weedb.create(self.database_dict)
            except weedb.DatabaseExistsError:
                pass
            return weedb.connect(self.database_dict)

    def _run(self, connection):
        """ The queue processing loop. """
        last_prune = time.time()
        while True:
            try:
                event = self.queue.get(timeout=self._prune_timeout())
            except queue.Empty:
                last_prune = self._maybe_prune(connection, last_prune)
                continue
            last_prune, stop = self._process_event(connection, event, last_prune)
            if stop:
                return

    def _process_event(self, connection, event, last_prune):
        """ Process one event, returning the next prune time and whether to stop. """
        if event[0] in _CONTROL_EVENTS:
            return self._maybe_prune(connection, last_prune), self._apply_control(connection, event)

        batch, control = self._collect(event)
        self._apply(connection, batch)
        last_prune = self._maybe_prune(connection, last_prune)
        return last_prune, control is not None and self._apply_control(connection, control)

    def _apply_control(self, connection, event):
        """ Apply a control event, returning whether the queue loop should stop. """
        if event[0] == _EVENT_FINALIZE:
            self._apply_finalize(connection, event[1])
            return True
        if event[0] == _EVENT_DISCONNECT:
            self._apply_disconnect(connection, event[1])
        else:
            self._apply_resend(connection, event[1], event[2], event[3])
        return False

    def _prune_timeout(self):
        """ The queue wait before an idle prune. """
        if self.prune_interval > 0 and self._has_retention():
            return self.prune_interval
        return None

    def _has_retention(self):
        """ Whether any row is ever pruned. """
        return (self.retention > 0 or
                self.unconfirmed_retention > 0 or
                any(retention > 0 for retention in self.topic_retention.values()) or
                any(retention > 0 for retention in self.topic_unconfirmed_retention.values()))

    def _maybe_prune(self, connection, last_prune):
        """ Prune when the interval has elapsed. """
        now = time.time()
        if self._has_retention() and 0 < self.prune_interval <= now - last_prune:
            self._prune(connection, now)
            return now
        return last_prune

    def _collect(self, event):
        """ Collect a batch of events, stopping when a control event is seen. """
        batch = [event]
        control = None
        while len(batch) < self.batch_size:
            try:
                item = self.queue.get_nowait()
            except queue.Empty:
                break
            if item[0] in _CONTROL_EVENTS:
                control = item
                break
            batch.append(item)
        return batch, control

    def _apply(self, connection, batch):
        """ Write one batch in a single transaction. """
        now = time.time()
        inflight = dict(self.inflight)
        pending = self._prune_pending(now)

        statements = []
        for event in batch:
            if event[0] == _EVENT_SENT:
                self._apply_sent(event, inflight, pending, statements, now)
            else:
                self._apply_arrived(event, inflight, pending, statements, now)

        if not self._write(connection, statements):
            return

        self.inflight = inflight
        self.pending = pending

    def _prune_pending(self, now):
        """ Drop arrivals that never matched a send event. """
        pending = dict(self.pending)
        for mid, (_, queued_at) in list(pending.items()):
            if now - queued_at > self.pending_ttl:
                del pending[mid]
        return pending

    def _apply_sent(self, event, inflight, pending, statements, now):  # pylint: disable=too-many-positional-arguments,too-many-arguments
        """ Add the statements for a send event. """
        # pylint: disable=too-many-locals
        _, row_id, mid, rc, topic, payload, payload_encoding, qos, retain, date_time, sent_ts = event
        status = STATUS_SENT if rc == _RC_SUCCESS else STATUS_FAILED
        statements.append((f"INSERT INTO {self.table} "
                           "(id, mid, dateTime, sent_ts, arrived_ts, status, unconfirmed_ts, "
                           "origin_id, attempt, clientid, topic, qos, retain, rc, payload, payload_encoding) "
                           "VALUES (?, ?, ?, ?, NULL, ?, NULL, NULL, NULL, NULL, ?, ?, ?, ?, ?, ?)",
                           (row_id, mid, date_time, sent_ts, status, topic, qos, retain, rc, payload,
                            payload_encoding)))
        if status != STATUS_SENT:
            return

        self._unconfirm_reused_mid(inflight, mid, statements, now)
        inflight[mid] = (row_id, sent_ts)
        if mid in pending:
            arrived_ts = pending.pop(mid)[0]
            statements.append((f"UPDATE {self.table} SET arrived_ts = ?, status = ? WHERE id = ?",
                               (arrived_ts, STATUS_CONFIRMED, row_id)))

    def _unconfirm_reused_mid(self, inflight, mid, statements, now):
        """ Mark the row of a message id that paho has reused as unconfirmed.

            The arrival of the older message will never be reported, so it is
            unconfirmed, not undelivered. """
        previous = inflight.pop(mid, None)
        if previous is None:
            return
        statements.append((f"UPDATE {self.table} SET status = ?, unconfirmed_ts = ? WHERE id = ? AND status = ?",
                           (STATUS_UNCONFIRMED, now, previous[0], STATUS_SENT)))

    def _apply_arrived(self, event, inflight, pending, statements, now):  # pylint: disable=too-many-positional-arguments
        """ Add the statements for an arrival event. """
        _, mid, arrived_ts = event
        previous = inflight.pop(mid, None)
        if previous is None:
            pending[mid] = (arrived_ts, now)
        else:
            statements.append((f"UPDATE {self.table} SET arrived_ts = ?, status = ? WHERE id = ? AND status = ?",
                               (arrived_ts, STATUS_CONFIRMED, previous[0], STATUS_SENT)))

    def _apply_finalize(self, connection, unconfirmed_ts):
        """ Mark the rows whose arrival paho never reported as unconfirmed. """
        rows = list(self.inflight.values())
        self.inflight = {}
        self._mark_unconfirmed(connection, rows, unconfirmed_ts, "no arrival was reported")

    def _apply_disconnect(self, connection, unconfirmed_ts):
        """ Mark the rows in flight when the connection was lost as unconfirmed. """
        rows = list(self.inflight.values())
        self.inflight = {}
        self._mark_unconfirmed(connection, rows, unconfirmed_ts, "the connection was lost")

    def _mark_unconfirmed(self, connection, rows, unconfirmed_ts, reason):
        """ Mark rows that are still sent as unconfirmed. """
        marked = 0
        for start in range(0, len(rows), self.batch_size):
            chunk = rows[start:start + self.batch_size]
            statements = [(f"UPDATE {self.table} SET status = ?, unconfirmed_ts = ? WHERE id = ? AND status = ?",
                           (STATUS_UNCONFIRMED, unconfirmed_ts, row_id, STATUS_SENT))
                          for row_id, _ in chunk]
            if not self._write(connection, statements):
                break
            marked += len(chunk)
        if marked:
            self._log('INFO', f"Marked {marked} message tracking rows as unconfirmed, {reason}.")

    def _apply_resend(self, connection, client, options, clientid):
        """ Publish the messages after the last confirmed publish on each topic. """
        rows = self._fetch_for_resend(connection)
        if rows is None:
            return

        selected = select_after_last_success(
            rows, since=options['since'],
            include_before_last_success=options['include_before_last_success'])
        if options['limit'] > 0:
            selected = selected[:options['limit']]
        if not selected:
            self._log('DEBUG', "No messages need to be resent after the connection was established.")
            return

        self._log('INFO', f"Resending {len(selected)} message(s) after the connection was established.")
        published = self._publish_resends(client, selected)
        if not published:
            return
        inserted = self._record_resends(connection, published, clientid)
        if inserted is None:
            return
        self._log_resend_summary(inserted)

    def _fetch_for_resend(self, connection):
        """ Read the rows for a resend, or None when they cannot be read. """
        try:
            return fetch_rows(connection, self.table)
        except Exception as exception:  # pylint: disable=broad-exception-caught
            self._log('ERROR', f"Unable to read the message tracking rows for a resend: {exception}.")
            return None

    def _publish_resends(self, client, selected):
        """ Publish the selected rows, returning what paho accepted. """
        published = []
        for row in selected:
            if self.shutting_down:
                self._log('INFO', "Stopping the resend because the message tracker is shutting down.")
                break
            published_row, stop = self._publish_resend(client, row)
            if published_row is not None:
                published.append(published_row)
            if stop:
                break
        return published

    def _publish_resend(self, client, row):
        """ Publish one resend, returning the outcome and whether the resend must stop. """
        try:
            payload = decode_payload(row)
        except ValueError as exception:
            self._log('ERROR', f"Unable to decode the payload of {row['id']}: {exception}.")
            return None, False

        try:
            message_info = client.publish(row['topic'], payload, qos=row['qos'], retain=bool(row['retain']))
        except Exception as exception:  # pylint: disable=broad-exception-caught
            self._log('ERROR', f"Unable to resend {row['topic']}: {exception}.")
            return None, False

        rc = int(message_info.rc)
        if rc == mqtt.MQTT_ERR_NO_CONN:
            self._log('ERROR', "The connection was lost while resending, "
                               "the remaining messages are left for the next connection.")
            return None, True
        return (row, message_info.mid, rc, time.time()), False

    def _record_resends(self, connection, published, clientid):
        """ Record the published rows, or None when they cannot be written. """
        try:
            inserted = self._insert_resends(connection, published, clientid)
        except Exception as exception:  # pylint: disable=broad-exception-caught
            self._log('ERROR', f"Unable to record the resent messages: {exception}.")
            return None
        self._finish_resends(connection, inserted)
        return inserted

    def _finish_resends(self, connection, inserted):
        """ Track the resent messages that are waiting for an arrival. """
        for row_id, mid, status, sent_ts in inserted:
            if status != STATUS_SENT:
                continue
            pending = self.pending.pop(mid, None)
            if pending is None:
                self.inflight[mid] = (row_id, sent_ts)
            else:
                self._ack_pending(connection, row_id, pending[0])

    def _log_resend_summary(self, inserted):
        """ Log what the resend published. """
        sent = sum(1 for _, _, status, _ in inserted if status == STATUS_SENT)
        failed = len(inserted) - sent
        self._log('INFO', f"Resent {len(inserted)} message(s), "
                          f"{sent} awaiting confirmation, {failed} failed.")

    def _insert_resends(self, connection, published, clientid):
        """ Insert the resend rows in one transaction, returning what was inserted. """
        inserted = []
        with weedb.Transaction(connection) as cursor:
            attempts = {}
            for row, mid, rc, sent_ts in published:
                row_origin_id = origin_id(row)
                if row_origin_id not in attempts:
                    attempts[row_origin_id] = next_attempt(cursor, self.table, row_origin_id)
                else:
                    attempts[row_origin_id] += 1
                status = STATUS_SENT if rc == _RC_SUCCESS else STATUS_FAILED
                row_id = uuid.uuid4().hex
                cursor.execute(
                    f"INSERT INTO {self.table} "
                    "(id, mid, dateTime, sent_ts, arrived_ts, status, unconfirmed_ts, "
                    "origin_id, attempt, clientid, topic, qos, retain, rc, payload, payload_encoding) "
                    "VALUES (?, ?, ?, ?, NULL, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (row_id, mid, row['dateTime'], sent_ts, status, row_origin_id,
                     attempts[row_origin_id], clientid, row['topic'], row['qos'], row['retain'],
                     rc, row['payload'], row['payload_encoding']))
                inserted.append((row_id, mid, status, sent_ts))
        return inserted

    def _ack_pending(self, connection, row_id, arrived_ts):
        """ Mark a resend as confirmed when its arrival was reported before it was recorded. """
        try:
            with weedb.Transaction(connection) as cursor:
                cursor.execute(f"UPDATE {self.table} SET status = ?, arrived_ts = ? WHERE id = ?",
                               (STATUS_CONFIRMED, arrived_ts, row_id))
        except Exception as exception:  # pylint: disable=broad-exception-caught
            self._log('ERROR', f"Unable to record the arrival of a resent message: {exception}.")

    def _sweep(self, connection):
        """ Mark the rows a previous run left waiting for an arrival as unconfirmed. """
        try:
            with weedb.Transaction(connection) as cursor:
                cursor.execute(f"SELECT COUNT(*) FROM {self.table} WHERE status = ?", (STATUS_SENT,))
                row = cursor.fetchone()
                stale = row[0] if row else 0
                cursor.execute(f"UPDATE {self.table} SET status = ?, unconfirmed_ts = ? WHERE status = ?",
                               (STATUS_UNCONFIRMED, time.time(), STATUS_SENT))
        except Exception as exception:  # pylint: disable=broad-exception-caught
            self._log('ERROR', f"Unable to mark the message tracking rows of a previous run as unconfirmed: {exception}.")
            return
        if stale:
            self._log('INFO', f"Marked {stale} message tracking rows from a previous run as unconfirmed.")

    def _write(self, connection, statements):
        """ Execute the batch, returning whether it was written. """
        try:
            with weedb.Transaction(connection) as cursor:
                for statement, args in statements:
                    cursor.execute(statement, args)
        except Exception as exception:  # pylint: disable=broad-exception-caught
            self._log('ERROR', f"Unable to write message tracking data: {exception}.")
            return False
        return True

    def _prune(self, connection, now):
        """ Delete rows that are older than their retention period.

            The confirmed and failed rows are pruned by 'retention'. The unconfirmed
            rows are pruned by 'unconfirmed_retention', which defaults to never.
            A sent row is left for the startup sweep. """
        try:
            self._prune_known_outcomes(connection, now)
            self._prune_unconfirmed(connection, now)
        except Exception as exception:  # pylint: disable=broad-exception-caught
            self._log('ERROR', f"Unable to prune message tracking data: {exception}.")

    def _prune_known_outcomes(self, connection, now):
        """ Prune the confirmed and failed rows, by the topic's retention. """
        self._delete_unlisted(connection, now, self.retention, self.topic_retention, _PRUNED_STATUSES)
        for topic, retention in self.topic_retention.items():
            if retention > 0:
                self._delete_topic(connection, topic, now, retention, _PRUNED_STATUSES)

    def _prune_unconfirmed(self, connection, now):
        """ Prune the unconfirmed rows, by the topic's unconfirmed retention. """
        if not self._has_unconfirmed_retention():
            return
        self._delete_unlisted(connection, now, self.unconfirmed_retention,
                              self.topic_unconfirmed_retention, (STATUS_UNCONFIRMED,))
        for topic, retention in self.topic_unconfirmed_retention.items():
            if retention > 0:
                self._delete_topic(connection, topic, now, retention, (STATUS_UNCONFIRMED,))

    def _has_unconfirmed_retention(self):
        """ Whether any unconfirmed row is ever pruned. """
        return (self.unconfirmed_retention > 0 or
                any(retention > 0 for retention in self.topic_unconfirmed_retention.values()))

    def _delete_topic(self, connection, topic, now, retention, statuses):
        """ Delete the rows of one topic. """
        placeholders = ', '.join('?' for _ in statuses)
        connection.execute(
            f"DELETE FROM {self.table} WHERE topic = ? AND sent_ts < ? AND status IN ({placeholders})",
            (topic, now - retention, *statuses))

    def _delete_unlisted(self, connection, now, retention, topic_retention, statuses):
        """ Delete the rows of topics that are no longer tracked, with the table-wide retention. """
        if retention <= 0:
            return
        topics = list(topic_retention)
        status_placeholders = ', '.join('?' for _ in statuses)
        if not topics:
            connection.execute(
                f"DELETE FROM {self.table} WHERE sent_ts < ? AND status IN ({status_placeholders})",
                (now - retention, *statuses))
            return
        topic_placeholders = ', '.join('?' for _ in topics)
        connection.execute(
            f"DELETE FROM {self.table} WHERE topic NOT IN ({topic_placeholders}) AND sent_ts < ? "
            f"AND status IN ({status_placeholders})",
            (*topics, now - retention, *statuses))

    def _put(self, event):
        """ Queue an event, dropping it rather than blocking the caller. """
        if not self.accepting:
            return
        try:
            self.queue.put_nowait(event)
        except queue.Full:
            self.dropped += 1
            if self.dropped == 1 or self.dropped % 1000 == 0:
                self._log('ERROR', f"Dropped {self.dropped} message tracking events, the queue is full.")

    def _drain(self):
        """ Discard queued events after the database could not be opened. """
        while True:
            try:
                event = self.queue.get_nowait()
            except queue.Empty:
                return
            if event[0] == _EVENT_FINALIZE:
                return

    @staticmethod
    def _payload(payload):
        """ Convert the payload to something the database can store, with its encoding. """
        if payload is None:
            return None, None
        if isinstance(payload, (bytes, bytearray)):
            return bytes(payload).hex(), 'hex'
        return str(payload), 'text'

    def _log(self, log_type, msg_text):
        self.logger_queue.put(user.mqttcommon.Logger.create_entry(self.log_name, log_type, None, msg_text))


class MQTTMessageTracker(user.mqttpublish.MQTTPlugin):  # pylint: disable=too-many-instance-attributes
    """ Track published MQTT messages in the WeeWX database. """

    def __init__(self, logger_queue, _monitor_config, name, plugin_dict, mqtt_dict, topics, weewx_dict):  # pylint: disable=R0913,R0917
        super().__init__(logger_queue, name, plugin_dict)

        self.tracker = None
        self.resend = None
        self.connect_count = 0
        self.mqtt_dict = mqtt_dict or {}
        self.topics = topics or {}
        self.tracked_topics = {}
        self.topic_unconfirmed_retentions = {}
        if not self.enabled:
            return

        self.retention = self._config_int(plugin_dict, 'retention', DEFAULT_RETENTION)
        self.unconfirmed_retention = self._config_int(
            plugin_dict, 'unconfirmed_retention', DEFAULT_UNCONFIRMED_RETENTION)
        self.tracked_topics, self.topic_unconfirmed_retentions = self._configure_topics(plugin_dict)
        if not self.tracked_topics:
            self.enabled = False
            return

        try:
            database_dict, table = resolve_tracker_config(plugin_dict, weewx_dict['config_dict'])
        except TrackerConfigError as exception:
            self._log('ERROR', str(exception))
            self.enabled = False
            return

        self.resend = self._configure_resend(plugin_dict)
        self.tracker = _TrackerThread(
            logger_queue,
            self.name,
            database_dict,
            table,
            self.retention,
            self.tracked_topics,
            self.unconfirmed_retention,
            self.topic_unconfirmed_retentions,
            self._config_int(plugin_dict, 'prune_interval', 3600),
            self._config_int(plugin_dict, 'batch_size', 100),
            self._config_int(plugin_dict, 'pending_ttl', 60),
            self._config_int(plugin_dict, 'queue_size', 10000),
            self._config_int(plugin_dict, 'shutdown_timeout', 10),
            to_bool(plugin_dict.get('create_database', True)),
        )
        self.tracker.start()

    def _configure_topics(self, plugin_dict):
        """ Resolve the topics to track, with the retention to prune each one by.

            A message published with qos 0 is never acknowledged, so its delivery cannot be
            confirmed. Recording it would either leave a row that can never become 'confirmed',
            or - worse - mark it 'confirmed' when paho has only written it to the socket. Such a
            topic is rejected with an error.
        """
        topic_dicts = plugin_dict.get('topics')
        if topic_dicts is None:
            self._log('ERROR', "'[[topics]]' is required, no messages are tracked.")
            return {}, {}

        tracked = topic_retentions(topic_dicts, self.retention)
        unconfirmed = topic_unconfirmed_retentions(topic_dicts, self.unconfirmed_retention)
        for topic in list(tracked):
            if self.topics.get(topic, {}).get('qos') == 0:
                self._log('ERROR', f"{topic} is published with qos 0, so its delivery cannot be confirmed. "
                                   "It is not tracked.")
                del tracked[topic]
                unconfirmed.pop(topic, None)

        if not tracked:
            self._log('ERROR', "No topics are enabled, no messages are tracked.")
        return tracked, unconfirmed

    def _configure_resend(self, plugin_dict):
        """ Resolve the automatic resend options, or None when they are not enabled. """
        resend_dict = plugin_dict.get('resend')
        if resend_dict is None or not to_bool(resend_dict.get('enable', False)):
            return None

        options = {
            'on_startup': to_bool(resend_dict.get('on_startup', True)),
            'on_reconnect': to_bool(resend_dict.get('on_reconnect', True)),
            'include_before_last_success': to_bool(resend_dict.get('include_before_last_success', False)),
            'since': max(0, self._config_int(resend_dict, 'since', 0)),
            'limit': max(0, self._config_int(resend_dict, 'limit', 0)),
        }
        if not options['on_startup'] and not options['on_reconnect']:
            self._log('ERROR', "The resend options disable both on_startup and on_reconnect, "
                               "no messages will be resent.")
            return None
        return options

    def _log(self, log_type, msg_text):
        self.logger_queue.put(user.mqttcommon.Logger.create_entry(self.name, log_type, None, msg_text))

    @staticmethod
    def _config_int(plugin_dict, key, default):
        """ Read an integer option, falling back to the default when it is empty. """
        value = to_int(plugin_dict.get(key, default))
        return default if value is None else value

    def get_callbacks(self):
        """ The callbacks. """
        if not self.enabled or self.tracker is None:
            return []

        callbacks = [
            {
                'mqtt_publish': {
                    'timing': 'delay',
                    'callback': self.mqtt_publish
                }
            },
            {
                'on_mqtt_publish': {
                    'timing': 'immediate',
                    'callback': self.on_mqtt_publish
                }
            },
            {
                'on_mqtt_disconnect': {
                    'timing': 'immediate',
                    'callback': self.on_mqtt_disconnect
                }
            },
        ]
        if self.resend is not None:
            callbacks.append({
                'on_mqtt_connect': {
                    'timing': 'immediate',
                    'callback': self.on_mqtt_connect
                }
            })
        return callbacks

    def mqtt_publish(self, _client, mid, rc, topic, payload, qos, retain, date_time):  # pylint: disable=R0913,R0917
        """ Record the message that was handed to paho. """
        if topic not in self.tracked_topics:
            return
        self.tracker.sent(mid, rc, topic, payload, qos, retain, date_time)

    def on_mqtt_publish(self, _client, _userdata, mid, _properties):
        """ Record that paho reported the message as published. """
        self.tracker.arrived(mid)

    def on_mqtt_connect(self, client, _userdata, _flags, _rc, _properties):
        """ Queue a resend after a successful connect or reconnect. """
        if self.resend is None:
            return
        self.connect_count += 1
        is_startup = self.connect_count == 1
        if is_startup and not self.resend['on_startup']:
            return
        if not is_startup and not self.resend['on_reconnect']:
            return
        self.tracker.resend(client, self.resend, self.mqtt_dict.get('clientid'))

    def on_mqtt_disconnect(self, _client, _userdata, _rc, _properties):
        """ Queue an event that marks the messages in flight as unconfirmed. """
        if self.tracker is not None:
            self.tracker.disconnected(time.time())

    def shutdown(self):
        """ Flush the queued events. """
        if self.tracker is not None:
            self.tracker.shutdown()

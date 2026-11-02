#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
""" Track published MQTT messages in the WeeWX database. """

# pylint: disable=wrong-import-order
import queue
import re
import threading
import time
import uuid

import weewx
import weewx.manager
import weedb
from weeutil.weeutil import to_bool, to_int

import user.mqttpublish
import user.mqttcommon


TABLE_NAME_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
DEFAULT_TABLE = 'mqtt_message_tracker'


class TrackerConfigError(Exception):
    """ A tracker option that prevents writing to the database. """


def resolve_tracker_config(plugin_dict, config_dict):
    """ Resolve the database and table a tracker writes to.

        Raises TrackerConfigError when the options cannot be used. """
    data_binding = plugin_dict.get('data_binding')
    if not data_binding:
        raise TrackerConfigError("The data_binding option is required and must name a separate database binding.")

    try:
        manager_dict = weewx.manager.get_manager_dict_from_config(config_dict, data_binding)
    except (KeyError, TypeError, weewx.UnknownBinding) as exception:
        raise TrackerConfigError(f"Unable to resolve data binding {data_binding}: {exception}") from exception

    table = plugin_dict.get('table', DEFAULT_TABLE)
    if not isinstance(table, str) or not TABLE_NAME_PATTERN.match(table):
        raise TrackerConfigError(f"Invalid table name, {table}.")

    return manager_dict['database_dict'], table

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

# The values of the status column.
_STATUS_FAILED = 'failed'
_STATUS_SENT = 'sent'
_STATUS_ACKED = 'acked'
_STATUS_UNCONFIRMED = 'unconfirmed'


class _TrackerThread(threading.Thread):  # pylint: disable=too-many-instance-attributes
    """ Write publish events to the database on a single thread. """

    def __init__(self, logger_queue, log_name, database_dict, table,  # pylint: disable=too-many-arguments,too-many-positional-arguments
                 retention, prune_interval, batch_size, pending_ttl, queue_size, shutdown_timeout,
                 create_database):
        threading.Thread.__init__(self)
        self.daemon = True

        self.logger_queue = logger_queue
        self.log_name = log_name
        self.database_dict = database_dict
        self.table = table
        self.retention = retention
        self.prune_interval = prune_interval
        self.batch_size = batch_size
        self.pending_ttl = pending_ttl
        self.shutdown_timeout = shutdown_timeout
        self.create_database = create_database

        self.queue = queue.Queue(maxsize=queue_size)
        self.accepting = True
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

    def shutdown(self):
        """ Stop the thread after it has written the queued events and closed the unconfirmed ones. """
        if not self.is_alive():
            return
        try:
            self.queue.put((_EVENT_FINALIZE, time.time()), timeout=self.shutdown_timeout)
        except queue.Full:
            self._log('ERROR', "Unable to queue the message tracker shutdown event.")
            return
        self.join(self.shutdown_timeout)
        if self.is_alive():
            self._log('ERROR', "The message tracker thread did not shut down.")

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
            self._log('ERROR', f"Unable to open the message tracker database: {exception}")
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

            if event[0] == _EVENT_FINALIZE:
                self._apply_finalize(connection, event[1])
                return

            batch, finalize_ts = self._collect(event)
            self._apply(connection, batch)
            last_prune = self._maybe_prune(connection, last_prune)

            if finalize_ts is not None:
                self._apply_finalize(connection, finalize_ts)
                return

    def _prune_timeout(self):
        """ The queue wait before an idle prune. """
        if self.retention > 0 and self.prune_interval > 0:
            return self.prune_interval
        return None

    def _maybe_prune(self, connection, last_prune):
        """ Prune when the interval has elapsed. """
        now = time.time()
        if self.retention > 0 and 0 < self.prune_interval <= now - last_prune:
            self._prune(connection, now)
            return now
        return last_prune

    def _collect(self, event):
        """ Collect a batch of events, stopping when the finalize event is seen. """
        batch = [event]
        finalize_ts = None
        while len(batch) < self.batch_size:
            try:
                item = self.queue.get_nowait()
            except queue.Empty:
                break
            if item[0] == _EVENT_FINALIZE:
                finalize_ts = item[1]
                break
            batch.append(item)
        return batch, finalize_ts

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
        status = _STATUS_SENT if rc == _RC_SUCCESS else _STATUS_FAILED
        statements.append((f"INSERT INTO {self.table} "
                           "(id, mid, dateTime, sent_ts, arrived_ts, status, unconfirmed_ts, "
                           "origin_id, attempt, clientid, topic, qos, retain, rc, payload, payload_encoding) "
                           "VALUES (?, ?, ?, ?, NULL, ?, NULL, NULL, NULL, NULL, ?, ?, ?, ?, ?, ?)",
                           (row_id, mid, date_time, sent_ts, status, topic, qos, retain, rc, payload,
                            payload_encoding)))
        if status != _STATUS_SENT:
            return

        self._close_reused_mid(inflight, mid, statements, now)
        inflight[mid] = (row_id, sent_ts)
        if mid in pending:
            arrived_ts = pending.pop(mid)[0]
            statements.append((f"UPDATE {self.table} SET arrived_ts = ?, status = ? WHERE id = ?",
                               (arrived_ts, _STATUS_ACKED, row_id)))

    def _close_reused_mid(self, inflight, mid, statements, now):
        """ Close the row of a message id that paho has reused.

            The arrival of the older message will never be reported, so it is
            unconfirmed, not undelivered. """
        previous = inflight.pop(mid, None)
        if previous is None:
            return
        statements.append((f"UPDATE {self.table} SET status = ?, unconfirmed_ts = ? WHERE id = ? AND status = ?",
                           (_STATUS_UNCONFIRMED, now, previous[0], _STATUS_SENT)))

    def _apply_arrived(self, event, inflight, pending, statements, now):  # pylint: disable=too-many-positional-arguments
        """ Add the statements for an arrival event. """
        _, mid, arrived_ts = event
        previous = inflight.pop(mid, None)
        if previous is None:
            pending[mid] = (arrived_ts, now)
        else:
            statements.append((f"UPDATE {self.table} SET arrived_ts = ?, status = ? WHERE id = ? AND status = ?",
                               (arrived_ts, _STATUS_ACKED, previous[0], _STATUS_SENT)))

    def _apply_finalize(self, connection, unconfirmed_ts):
        """ Close the rows whose arrival paho never reported. """
        rows = list(self.inflight.values())
        self.inflight = {}
        closed = 0
        for start in range(0, len(rows), self.batch_size):
            chunk = rows[start:start + self.batch_size]
            statements = [(f"UPDATE {self.table} SET status = ?, unconfirmed_ts = ? WHERE id = ? AND status = ?",
                           (_STATUS_UNCONFIRMED, unconfirmed_ts, row_id, _STATUS_SENT))
                          for row_id, _ in chunk]
            if not self._write(connection, statements):
                break
            closed += len(chunk)
        if closed:
            self._log('INFO', f"Closed {closed} message tracking rows as unconfirmed.")

    def _sweep(self, connection):
        """ Close the rows a previous run left waiting for an arrival. """
        try:
            with weedb.Transaction(connection) as cursor:
                cursor.execute(f"UPDATE {self.table} SET status = ?, unconfirmed_ts = ? WHERE status = ?",
                               (_STATUS_UNCONFIRMED, time.time(), _STATUS_SENT))
        except Exception as exception:  # pylint: disable=broad-exception-caught
            self._log('ERROR', f"Unable to close the message tracking rows of a previous run: {exception}")

    def _write(self, connection, statements):
        """ Execute the batch, returning whether it was written. """
        try:
            with weedb.Transaction(connection) as cursor:
                for statement, args in statements:
                    cursor.execute(statement, args)
        except Exception as exception:  # pylint: disable=broad-exception-caught
            self._log('ERROR', f"Unable to write message tracking data: {exception}")
            return False
        return True

    def _prune(self, connection, now):
        """ Delete rows that are older than the retention period. """
        if self.retention <= 0:
            return
        try:
            connection.execute(f"DELETE FROM {self.table} WHERE sent_ts < ?", (now - self.retention,))
        except Exception as exception:  # pylint: disable=broad-exception-caught
            self._log('ERROR', f"Unable to prune message tracking data: {exception}")

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


class MQTTMessageTracker(user.mqttpublish.MQTTPlugin):
    """ Track published MQTT messages in the WeeWX database. """

    def __init__(self, logger_queue, _monitor_config, name, plugin_dict, _mqtt_dict, _topics, weewx_dict):  # pylint: disable=R0913,R0917
        super().__init__(logger_queue, name, plugin_dict)

        self.tracker = None
        if not self.enabled:
            return

        try:
            database_dict, table = resolve_tracker_config(plugin_dict, weewx_dict['config_dict'])
        except TrackerConfigError as exception:
            self.logger_queue.put(user.mqttcommon.Logger.create_entry(
                self.name, 'ERROR', None, str(exception)))
            self.enabled = False
            return

        self.tracker = _TrackerThread(
            logger_queue,
            self.name,
            database_dict,
            table,
            self._config_int(plugin_dict, 'retention', 604800),
            self._config_int(plugin_dict, 'prune_interval', 3600),
            self._config_int(plugin_dict, 'batch_size', 100),
            self._config_int(plugin_dict, 'pending_ttl', 60),
            self._config_int(plugin_dict, 'queue_size', 10000),
            self._config_int(plugin_dict, 'shutdown_timeout', 10),
            to_bool(plugin_dict.get('create_database', True)),
        )
        self.tracker.start()

    @staticmethod
    def _config_int(plugin_dict, key, default):
        """ Read an integer option, falling back to the default when it is empty. """
        value = to_int(plugin_dict.get(key, default))
        return default if value is None else value

    def get_callbacks(self):
        """ The callbacks. """
        if not self.enabled or self.tracker is None:
            return []

        return [
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
        ]

    def mqtt_publish(self, _client, mid, rc, topic, payload, qos, retain, date_time):  # pylint: disable=R0913,R0917
        """ Record the message that was handed to paho. """
        self.tracker.sent(mid, rc, topic, payload, qos, retain, date_time)

    def on_mqtt_publish(self, _client, _userdata, mid, _properties):
        """ Record that paho reported the message as published. """
        self.tracker.arrived(mid)

    def shutdown(self):
        """ Flush the queued events. """
        if self.tracker is not None:
            self.tracker.shutdown()

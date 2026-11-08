#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name
import os
import tempfile
import time
import unittest

import configobj
import mock
import paho.mqtt.client as mqtt

import helpers

import user.mqttmessagetracker
import weedb

TRACKED_TOPICS = ('topic', 'topic/one', 'topic/two', 'a', 'b', 'c', 'first', 'second', 'old', 'new')


def topics_config(topics):
    """ Build a [[topics]] section from a list of names or a dict of options. """
    if isinstance(topics, dict):
        return {topic: dict(options) for topic, options in topics.items()}
    return {topic: {'enable': True} for topic in topics}


class TestReadConfig(unittest.TestCase):
    def test_missing_file(self):
        with self.assertRaises(user.mqttmessagetracker.TrackerConfigError):
            user.mqttmessagetracker.read_config('/does/not/exist/weewx.conf')

    def test_supplies_weewx_root(self):
        # The tools read weewx.conf themselves, so they must supply WEEWX_ROOT the
        # way that WeeWX does, or SQLITE_ROOT cannot be resolved.
        with tempfile.TemporaryDirectory() as temp_dir:  # pylint: disable=consider-using-with
            config_file = os.path.join(temp_dir, 'weewx.conf')
            with open(config_file, 'w', encoding='utf-8') as file_object:
                file_object.write(
                    "[DataBindings]\n"
                    "    [[tracker_binding]]\n"
                    "        database = tracker\n"
                    "[Databases]\n"
                    "    [[tracker]]\n"
                    "        database_name = tracker.sdb\n"
                    "        database_type = SQLite\n"
                    "[DatabaseTypes]\n"
                    "    [[SQLite]]\n"
                    "        driver = weedb.sqlite\n"
                    "        SQLITE_ROOT = archive\n"
                    "[MQTTMessageTracker]\n"
                    "    data_binding = tracker_binding\n")

            config = user.mqttmessagetracker.read_config(config_file)
            _plugin_dict, database_dict, table = user.mqttmessagetracker.tool_config(config)

            self.assertEqual(config['WEEWX_ROOT'], temp_dir)
            self.assertEqual(database_dict['SQLITE_ROOT'], os.path.join(temp_dir, 'archive'))
            self.assertEqual(database_dict['database_name'], 'tracker.sdb')
            self.assertEqual(table, 'mqtt_message_tracker')


def make_row(row_id, topic, status, sent_ts, origin_id=None):
    """ A row as the resend selection sees it. """
    return {'id': row_id, 'topic': topic, 'status': status, 'sent_ts': sent_ts, 'origin_id': origin_id}


class TestSelectAfterLastSuccess(unittest.TestCase):
    def test_resends_the_tail_after_the_last_success(self):
        rows = [
            make_row('acked-1', 'topic', user.mqttmessagetracker.STATUS_ACKED, 1),
            make_row('failed', 'topic', user.mqttmessagetracker.STATUS_FAILED, 2),
            make_row('acked-2', 'topic', user.mqttmessagetracker.STATUS_ACKED, 3),
            make_row('unconfirmed', 'topic', user.mqttmessagetracker.STATUS_UNCONFIRMED, 4),
            make_row('failed-2', 'topic', user.mqttmessagetracker.STATUS_FAILED, 5),
        ]

        selected = user.mqttmessagetracker.select_after_last_success(rows)

        self.assertEqual([row['id'] for row in selected], ['unconfirmed', 'failed-2'])

    def test_no_success_resends_every_failed_and_unconfirmed_row(self):
        rows = [
            make_row('unconfirmed', 'topic', user.mqttmessagetracker.STATUS_UNCONFIRMED, 2),
            make_row('failed', 'topic', user.mqttmessagetracker.STATUS_FAILED, 1),
            make_row('sent', 'topic', user.mqttmessagetracker.STATUS_SENT, 3),
        ]

        selected = user.mqttmessagetracker.select_after_last_success(rows)

        self.assertEqual([row['id'] for row in selected], ['failed', 'unconfirmed'])

    def test_the_boundary_is_per_topic(self):
        rows = [
            make_row('a-acked', 'a', user.mqttmessagetracker.STATUS_ACKED, 1),
            make_row('a-failed', 'a', user.mqttmessagetracker.STATUS_FAILED, 2),
            make_row('b-acked', 'b', user.mqttmessagetracker.STATUS_ACKED, 10),
            make_row('b-failed', 'b', user.mqttmessagetracker.STATUS_FAILED, 11),
        ]

        selected = user.mqttmessagetracker.select_after_last_success(rows)

        self.assertEqual([row['id'] for row in selected], ['a-failed', 'b-failed'])

    def test_an_acked_resend_confirms_the_original_without_moving_the_boundary(self):
        rows = [
            make_row('origin', 'topic', user.mqttmessagetracker.STATUS_UNCONFIRMED, 1),
            make_row('resend', 'topic', user.mqttmessagetracker.STATUS_ACKED, 10, origin_id='origin'),
            make_row('failed', 'topic', user.mqttmessagetracker.STATUS_FAILED, 2),
        ]

        selected = user.mqttmessagetracker.select_after_last_success(rows)

        # The resend's sent_ts must not hide the older failed row.
        self.assertEqual([row['id'] for row in selected], ['failed'])

    def test_an_origin_is_resent_once(self):
        rows = [
            make_row('origin', 'topic', user.mqttmessagetracker.STATUS_UNCONFIRMED, 1),
            make_row('resend-1', 'topic', user.mqttmessagetracker.STATUS_UNCONFIRMED, 2, origin_id='origin'),
            make_row('resend-2', 'topic', user.mqttmessagetracker.STATUS_FAILED, 3, origin_id='origin'),
        ]

        selected = user.mqttmessagetracker.select_after_last_success(rows)

        self.assertEqual([row['id'] for row in selected], ['origin'])

    def test_since_bounds_the_age(self):
        rows = [
            make_row('old', 'topic', user.mqttmessagetracker.STATUS_FAILED, 100),
            make_row('new', 'topic', user.mqttmessagetracker.STATUS_FAILED, 200),
        ]

        selected = user.mqttmessagetracker.select_after_last_success(rows, since=50, now=250)

        self.assertEqual([row['id'] for row in selected], ['new'])


class TestMQTTMessageTracker(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.temp_dir.cleanup)

        self.database_dict = {
            'driver': 'weedb.sqlite',
            'database_name': 'tracker.sdb',
            'SQLITE_ROOT': self.temp_dir.name,
        }

        self.config_dict = configobj.ConfigObj({
            'WEEWX_ROOT': self.temp_dir.name,
            'DataBindings': {
                'tracker_binding': {
                    'database': 'tracker',
                },
            },
            'Databases': {
                'tracker': self.database_dict,
            },
        })
        self.weewx_dict = {'config_dict': self.config_dict}

    def _make_plugin(self, plugin_dict=None, set_binding=True, topics=TRACKED_TOPICS, publish_topics=None,
                     mqtt_dict=None):
        plugin_dict = dict(plugin_dict or {})
        if set_binding:
            plugin_dict.setdefault('data_binding', 'tracker_binding')
        if topics is not None:
            plugin_dict['topics'] = topics_config(topics)

        logger_queue = mock.Mock()
        plugin = user.mqttmessagetracker.MQTTMessageTracker(logger_queue,
                                                            None,
                                                            'MQTTMessageTracker',
                                                            configobj.ConfigObj(plugin_dict),
                                                            mqtt_dict,
                                                            publish_topics,
                                                            self.weewx_dict)
        self.addCleanup(plugin.shutdown)
        return plugin, logger_queue

    def _rows(self, table='mqtt_message_tracker'):
        connection = weedb.connect(self.database_dict)
        try:
            cursor = connection.cursor()
            cursor.execute(f"SELECT id, mid, dateTime, sent_ts, arrived_ts, status, unconfirmed_ts, "
                           f"origin_id, attempt, clientid, topic, qos, retain, rc, payload, payload_encoding "
                           f"FROM {table} ORDER BY sent_ts, id")
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            connection.close()

    def _wait_for(self, predicate, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                rows = self._rows()
            except weedb.DatabaseError:
                rows = []
            if predicate(rows):
                return rows
            time.sleep(0.01)
        self.fail("The tracker did not reach the expected state.")

    def _wait_for_rows(self, count, timeout=5):
        return self._wait_for(lambda rows: len(rows) >= count, timeout)

    def _wait_for_log(self, logger_queue, text, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if any(text in call[0][0]['msg_text'] for call in logger_queue.put.call_args_list):
                return
            time.sleep(0.01)
        self.fail(f"The log did not contain {text!r}.")

    def _insert_sent_row(self, mid, payload):
        connection = weedb.connect(self.database_dict)
        try:
            with weedb.Transaction(connection) as cursor:
                cursor.execute("INSERT INTO mqtt_message_tracker "
                               "(id, mid, dateTime, sent_ts, arrived_ts, status, unconfirmed_ts, "
                               "topic, qos, retain, rc, payload) "
                               "VALUES (?, ?, ?, ?, NULL, ?, NULL, ?, ?, ?, ?, ?)",
                               ('a' * 32, mid, 1, time.time(), 'sent', 'topic', 0, 0, 0, payload))
        finally:
            connection.close()

    def test_resolve_tracker_config(self):
        database_dict, table = user.mqttmessagetracker.resolve_tracker_config(
            {'data_binding': 'tracker_binding'}, self.config_dict)

        self.assertEqual(database_dict['database_name'], 'tracker.sdb')
        self.assertEqual(table, 'mqtt_message_tracker')

        _, custom_table = user.mqttmessagetracker.resolve_tracker_config(
            {'data_binding': 'tracker_binding', 'table': 'custom_tracker'}, self.config_dict)

        self.assertEqual(custom_table, 'custom_tracker')

    def test_resolve_tracker_config_rejects_invalid_table(self):
        with self.assertRaises(user.mqttmessagetracker.TrackerConfigError):
            user.mqttmessagetracker.resolve_tracker_config(
                {'data_binding': 'tracker_binding', 'table': 'bad name'}, self.config_dict)

    def test_get_callbacks(self):
        plugin, _ = self._make_plugin()

        callbacks = plugin.get_callbacks()

        self.assertEqual(callbacks[0]['mqtt_publish']['timing'], 'delay')
        self.assertEqual(callbacks[0]['mqtt_publish']['callback'], plugin.mqtt_publish)
        self.assertEqual(callbacks[1]['on_mqtt_publish']['timing'], 'immediate')
        self.assertEqual(callbacks[1]['on_mqtt_publish']['callback'], plugin.on_mqtt_publish)
        self.assertEqual(callbacks[2]['on_mqtt_disconnect']['timing'], 'immediate')
        self.assertEqual(callbacks[2]['on_mqtt_disconnect']['callback'], plugin.on_mqtt_disconnect)
        self.assertEqual(len(callbacks), 3)

    def test_get_callbacks_includes_connect_when_resend_is_enabled(self):
        plugin, _ = self._make_plugin({'resend': {'enable': True}})

        callbacks = plugin.get_callbacks()

        self.assertEqual(callbacks[3]['on_mqtt_connect']['timing'], 'immediate')
        self.assertEqual(callbacks[3]['on_mqtt_connect']['callback'], plugin.on_mqtt_connect)

    def test_resend_options_default(self):
        plugin, _ = self._make_plugin({'resend': {'enable': True}})

        self.assertEqual(plugin.resend, {'on_startup': True, 'on_reconnect': True, 'since': 0, 'limit': 0})

    def test_resend_disabled_by_default(self):
        plugin, _ = self._make_plugin()

        self.assertIsNone(plugin.resend)

    def test_creates_missing_database(self):
        database_path = os.path.join(self.temp_dir.name, 'tracker.sdb')
        self.assertFalse(os.path.exists(database_path))

        plugin, _ = self._make_plugin()
        plugin.mqtt_publish(None, 1, 0, 'topic', 'payload', 0, False, 1)
        plugin.shutdown()

        self.assertTrue(os.path.exists(database_path))
        self.assertEqual(len(self._rows()), 1)

    def test_create_database_disabled(self):
        database_path = os.path.join(self.temp_dir.name, 'tracker.sdb')

        plugin, logger_queue = self._make_plugin({'create_database': False})
        plugin.mqtt_publish(None, 1, 0, 'topic', 'payload', 0, False, 1)
        plugin.shutdown()

        self.assertFalse(os.path.exists(database_path))
        log_messages = [call[0][0] for call in logger_queue.put.call_args_list]
        self.assertTrue(any(entry['log_type'] == 'ERROR' for entry in log_messages))

    def test_tracks_sent_and_arrived(self):
        plugin, _ = self._make_plugin()

        plugin.mqtt_publish(None, 42, 0, 'topic/one', 'payload', 1, False, 123456)
        plugin.on_mqtt_publish(None, None, 42, None)
        plugin.shutdown()

        rows = self._rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(len(row['id']), 32)
        self.assertEqual(row['mid'], 42)
        self.assertEqual(row['dateTime'], 123456)
        self.assertIsNotNone(row['sent_ts'])
        self.assertIsNotNone(row['arrived_ts'])
        self.assertEqual(row['status'], 'acked')
        self.assertIsNone(row['unconfirmed_ts'])
        self.assertEqual(row['topic'], 'topic/one')
        self.assertEqual(row['qos'], 1)
        self.assertEqual(row['retain'], 0)
        self.assertEqual(row['rc'], 0)
        self.assertEqual(row['payload'], 'payload')
        self.assertEqual(row['payload_encoding'], 'text')
        self.assertIsNone(row['origin_id'])
        self.assertIsNone(row['attempt'])
        self.assertIsNone(row['clientid'])

    def test_sent_until_arrival(self):
        plugin, _ = self._make_plugin()

        plugin.mqtt_publish(None, 42, 0, 'topic', 'payload', 0, False, 1)
        rows = self._wait_for_rows(1)

        self.assertEqual(rows[0]['status'], 'sent')
        self.assertIsNone(rows[0]['arrived_ts'])
        self.assertIsNone(rows[0]['unconfirmed_ts'])

        plugin.on_mqtt_publish(None, None, 42, None)
        rows = self._wait_for(lambda rows: rows and rows[0]['status'] == 'acked')

        self.assertIsNotNone(rows[0]['arrived_ts'])

    def test_connection_loss_marks_inflight_rows_unconfirmed(self):
        plugin, logger_queue = self._make_plugin()

        plugin.mqtt_publish(None, 42, 0, 'topic', 'payload', 1, False, 1)
        self._wait_for_rows(1)

        plugin.on_mqtt_disconnect(None, None, 1, None)

        rows = self._wait_for(lambda rows: rows and rows[0]['status'] == 'unconfirmed')
        self.assertIsNone(rows[0]['arrived_ts'])
        self.assertIsNotNone(rows[0]['unconfirmed_ts'])
        self._wait_for_log(logger_queue, "the connection was lost")

    def test_connection_loss_does_not_change_acked_rows(self):
        plugin, _ = self._make_plugin()

        plugin.mqtt_publish(None, 1, 0, 'topic', 'acked', 1, False, 1)
        plugin.on_mqtt_publish(None, None, 1, None)
        plugin.mqtt_publish(None, 2, 0, 'topic', 'sent', 1, False, 2)
        self._wait_for(lambda rows: any(row['status'] == 'acked' for row in rows) and len(rows) == 2)

        plugin.on_mqtt_disconnect(None, None, 1, None)

        rows = self._wait_for(lambda rows: any(row['status'] == 'unconfirmed' for row in rows))
        by_payload = {row['payload']: row for row in rows}
        self.assertEqual(by_payload['acked']['status'], 'acked')
        self.assertEqual(by_payload['sent']['status'], 'unconfirmed')

    def test_resend_after_connect(self):
        plugin, _ = self._make_plugin({'resend': {'enable': True}}, mqtt_dict={'clientid': 'test-client'})

        plugin.mqtt_publish(None, 1, 0, 'topic', 'acked', 1, False, 1)
        plugin.on_mqtt_publish(None, None, 1, None)
        self._wait_for(lambda rows: len(rows) == 1 and rows[0]['status'] == 'acked')
        time.sleep(0.01)
        plugin.mqtt_publish(None, 2, 1, 'topic', 'failed', 1, False, 2)
        rows = self._wait_for_rows(2)
        failed = [row for row in rows if row['payload'] == 'failed'][0]

        client = mock.Mock()
        client.publish.return_value = mock.Mock(mid=11, rc=0)
        plugin.on_mqtt_connect(client, None, 0, 0, None)

        rows = self._wait_for_rows(3)
        client.publish.assert_called_once_with('topic', 'failed', qos=1, retain=False)
        resent = [row for row in rows if row['origin_id'] == failed['id']][0]
        self.assertEqual(resent['attempt'], 1)
        self.assertEqual(resent['clientid'], 'test-client')
        self.assertEqual(resent['status'], 'sent')
        self.assertEqual(resent['payload'], 'failed')

        plugin.on_mqtt_publish(None, None, 11, None)
        rows = self._wait_for(lambda rows: any(row['id'] == resent['id'] and row['status'] == 'acked'
                                               for row in rows))
        by_id = {row['id']: row for row in rows}
        self.assertEqual(by_id[failed['id']]['status'], 'failed')
        self.assertEqual(by_id[resent['id']]['status'], 'acked')

    def test_resend_uses_the_last_success_as_the_boundary(self):
        plugin, _ = self._make_plugin({'resend': {'enable': True}})

        plugin.mqtt_publish(None, 1, 0, 'topic', 'acked-1', 1, False, 1)
        plugin.on_mqtt_publish(None, None, 1, None)
        self._wait_for(lambda rows: len(rows) == 1 and rows[0]['status'] == 'acked')
        time.sleep(0.01)
        plugin.mqtt_publish(None, 2, 1, 'topic', 'failed-before', 1, False, 2)
        self._wait_for_rows(2)
        time.sleep(0.01)
        plugin.mqtt_publish(None, 3, 0, 'topic', 'acked-2', 1, False, 3)
        plugin.on_mqtt_publish(None, None, 3, None)
        self._wait_for(lambda rows: any(row['payload'] == 'acked-2' and row['status'] == 'acked'
                                        for row in rows))
        time.sleep(0.01)
        plugin.mqtt_publish(None, 4, 1, 'topic', 'failed-after', 1, False, 4)
        self._wait_for_rows(4)

        client = mock.Mock()
        client.publish.return_value = mock.Mock(mid=11, rc=0)
        plugin.on_mqtt_connect(client, None, 0, 0, None)

        rows = self._wait_for_rows(5)
        client.publish.assert_called_once_with('topic', 'failed-after', qos=1, retain=False)
        self.assertFalse(any(row['payload'] == 'failed-before' and row['origin_id'] for row in rows))

    def test_resend_on_reconnect_only(self):
        plugin, _ = self._make_plugin(
            {'resend': {'enable': True, 'on_startup': False, 'on_reconnect': True}})

        plugin.mqtt_publish(None, 1, 1, 'topic', 'failed', 1, False, 1)
        self._wait_for_rows(1)

        client = mock.Mock()
        client.publish.return_value = mock.Mock(mid=11, rc=0)
        plugin.on_mqtt_connect(client, None, 0, 0, None)
        time.sleep(0.05)
        client.publish.assert_not_called()

        plugin.on_mqtt_connect(client, None, 0, 0, None)

        self._wait_for_rows(2)
        client.publish.assert_called_once_with('topic', 'failed', qos=1, retain=False)

    def test_resend_stops_when_the_connection_is_lost(self):
        plugin, logger_queue = self._make_plugin({'resend': {'enable': True}})

        plugin.mqtt_publish(None, 1, 1, 'topic', 'failed', 1, False, 1)
        self._wait_for_rows(1)

        client = mock.Mock()
        client.publish.return_value = mock.Mock(mid=11, rc=mqtt.MQTT_ERR_NO_CONN)
        plugin.on_mqtt_connect(client, None, 0, 0, None)

        self._wait_for_log(logger_queue, "The connection was lost while resending")
        self.assertEqual(len(self._rows()), 1)

    def test_failed_publish(self):
        plugin, _ = self._make_plugin()

        plugin.mqtt_publish(None, 5, 1, 'topic', 'payload', 1, False, 1)
        plugin.on_mqtt_publish(None, None, 5, None)
        plugin.shutdown()

        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'failed')
        self.assertEqual(rows[0]['rc'], 1)
        self.assertIsNone(rows[0]['arrived_ts'])
        self.assertIsNone(rows[0]['unconfirmed_ts'])

    def test_shutdown_logs_that_it_is_shutting_down(self):
        plugin, logger_queue = self._make_plugin()
        plugin.shutdown()

        self._wait_for_log(logger_queue, "Shutting down.")
        self._wait_for_log(logger_queue, "Message tracker is shut down.")

    def test_shutdown_logs_when_the_thread_does_not_stop(self):
        plugin, logger_queue = self._make_plugin()
        tracker = plugin.tracker
        tracker.shutdown_timeout = 3

        with mock.patch.object(tracker, 'join'), mock.patch.object(tracker, 'is_alive', return_value=True):
            tracker.shutdown()

        self._wait_for_log(logger_queue, "Message tracker did not shut down within 3 seconds.")

    def test_shutdown_marks_unreported_rows_unconfirmed(self):
        plugin, _ = self._make_plugin()

        start = time.time()
        plugin.mqtt_publish(None, 42, 0, 'topic', 'payload', 1, False, 1)
        plugin.shutdown()
        end = time.time()

        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'unconfirmed')
        self.assertIsNone(rows[0]['arrived_ts'])
        self.assertGreaterEqual(rows[0]['unconfirmed_ts'], start)
        self.assertLessEqual(rows[0]['unconfirmed_ts'], end)

    def test_mid_reuse_marks_previous_row_unconfirmed(self):
        plugin, _ = self._make_plugin()

        plugin.mqtt_publish(None, 42, 0, 'first', 'payload-one', 0, False, 1)
        plugin.mqtt_publish(None, 42, 0, 'second', 'payload-two', 0, False, 2)

        rows = self._wait_for_rows(2)
        by_payload = {row['payload']: row for row in rows}
        self.assertEqual(by_payload['payload-one']['status'], 'unconfirmed')
        self.assertIsNotNone(by_payload['payload-one']['unconfirmed_ts'])
        self.assertEqual(by_payload['payload-two']['status'], 'sent')

        reuse_ts = by_payload['payload-one']['unconfirmed_ts']
        plugin.shutdown()

        by_payload = {row['payload']: row for row in self._rows()}
        self.assertEqual(by_payload['payload-one']['unconfirmed_ts'], reuse_ts)
        self.assertEqual(by_payload['payload-two']['status'], 'unconfirmed')
        self.assertGreaterEqual(by_payload['payload-two']['unconfirmed_ts'], reuse_ts)

    def test_startup_marks_leftover_rows_unconfirmed(self):
        plugin, _ = self._make_plugin()
        plugin.mqtt_publish(None, 1, 0, 'topic', 'payload', 0, False, 1)
        plugin.on_mqtt_publish(None, None, 1, None)
        plugin.shutdown()

        self._insert_sent_row(2, 'leftover')

        # A new tracker marks the rows the previous run left waiting for an arrival.
        _, logger_queue = self._make_plugin()

        rows = self._wait_for(lambda rows: all(row['status'] != 'sent' for row in rows))
        self.assertEqual(len(rows), 2)
        leftover = [row for row in rows if row['payload'] == 'leftover'][0]
        self.assertEqual(leftover['status'], 'unconfirmed')
        self.assertIsNotNone(leftover['unconfirmed_ts'])
        self.assertIsNone(leftover['arrived_ts'])
        self._wait_for_log(logger_queue, "Marked 1 message tracking rows from a previous run")

    def test_arrival_before_send(self):
        plugin, _ = self._make_plugin()

        plugin.on_mqtt_publish(None, None, 7, None)
        plugin.mqtt_publish(None, 7, 0, 'topic/two', 'payload', 0, True, 1)
        plugin.shutdown()

        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'acked')
        self.assertIsNotNone(rows[0]['arrived_ts'])
        self.assertIsNone(rows[0]['unconfirmed_ts'])

    def test_unknown_arrival_is_ignored(self):
        plugin, _ = self._make_plugin()

        plugin.on_mqtt_publish(None, None, 99, None)
        plugin.shutdown()

        self.assertEqual(self._rows(), [])

    def test_payload_types(self):
        plugin, _ = self._make_plugin()

        plugin.mqtt_publish(None, 1, 0, 'a', bytearray(b'abc'), 0, False, 1)
        plugin.mqtt_publish(None, 2, 0, 'b', 12.5, 0, False, 2)
        plugin.mqtt_publish(None, 3, 0, 'c', None, 0, False, 3)
        plugin.shutdown()

        rows = self._rows()
        self.assertEqual([row['payload'] for row in rows], ['616263', '12.5', None])
        self.assertEqual([row['payload_encoding'] for row in rows], ['hex', 'text', None])

    def test_custom_table(self):
        plugin, _ = self._make_plugin({'table': 'custom_tracker'})

        plugin.mqtt_publish(None, 1, 0, 'topic', 'payload', 0, False, 1)
        plugin.shutdown()

        self.assertEqual(len(self._rows('custom_tracker')), 1)

    def test_prunes_old_rows(self):
        plugin, _ = self._make_plugin({'retention': 1, 'prune_interval': 1})

        plugin.mqtt_publish(None, 1, 0, 'old', 'payload', 0, False, 1)
        self._wait_for_rows(1)
        plugin.on_mqtt_publish(None, None, 1, None)
        self._wait_for(lambda rows: rows[0]['status'] == 'acked')

        time.sleep(1.1)
        plugin.mqtt_publish(None, 2, 0, 'new', 'payload', 0, False, 2)
        plugin.on_mqtt_publish(None, None, 2, None)
        plugin.shutdown()

        rows = self._rows()
        self.assertEqual([row['mid'] for row in rows], [2])

    def test_topic_retention(self):
        plugin, _ = self._make_plugin(
            {'retention': 60, 'unconfirmed_retention': 90},
            topics={'default': {}, 'custom': {'retention': 120, 'unconfirmed_retention': 180}})

        self.assertEqual(plugin.tracked_topics, {'default': 60, 'custom': 120})
        self.assertEqual(plugin.topic_unconfirmed_retentions, {'default': 90, 'custom': 180})

    def test_qos_zero_topic_is_not_tracked(self):
        plugin, logger_queue = self._make_plugin(
            topics={'qos0': {}, 'qos1': {}},
            publish_topics={'qos0': {'qos': 0}, 'qos1': {'qos': 1}})

        self.assertEqual(list(plugin.tracked_topics), ['qos1'])
        self.assertNotIn('qos0', plugin.topic_unconfirmed_retentions)
        messages = [call[0][0]['msg_text'] for call in logger_queue.put.call_args_list]
        self.assertTrue(any('qos0' in message and 'qos 0' in message for message in messages))

    def test_only_qos_zero_topics_disables_the_tracker(self):
        plugin, _ = self._make_plugin(topics=['qos0'], publish_topics={'qos0': {'qos': 0}})

        self.assertFalse(plugin.enabled)
        self.assertIsNone(plugin.tracker)

    def test_only_configured_topics_are_tracked(self):
        plugin, _ = self._make_plugin(topics=['tracked'])

        plugin.mqtt_publish(None, 1, 0, 'tracked', 'payload', 0, False, 1)
        plugin.mqtt_publish(None, 2, 0, 'other', 'payload', 0, False, 2)
        plugin.shutdown()

        self.assertEqual([row['topic'] for row in self._rows()], ['tracked'])

    def test_disabled_topic_is_not_tracked(self):
        plugin, _ = self._make_plugin(topics={'tracked': {}, 'off': {'enable': False}})

        plugin.mqtt_publish(None, 1, 0, 'tracked', 'payload', 0, False, 1)
        plugin.mqtt_publish(None, 2, 0, 'off', 'payload', 0, False, 2)
        plugin.shutdown()

        self.assertEqual([row['topic'] for row in self._rows()], ['tracked'])

    def test_per_topic_retention(self):
        plugin, _ = self._make_plugin({'retention': 3600, 'prune_interval': 1},
                                      topics={'short': {'retention': 1}, 'long': {}})

        plugin.mqtt_publish(None, 1, 0, 'short', 'payload', 0, False, 1)
        plugin.mqtt_publish(None, 2, 0, 'long', 'payload', 0, False, 2)
        self._wait_for_rows(2)
        plugin.on_mqtt_publish(None, None, 1, None)
        plugin.on_mqtt_publish(None, None, 2, None)
        self._wait_for(lambda rows: all(row['status'] == 'acked' for row in rows))

        time.sleep(1.1)
        plugin.mqtt_publish(None, 3, 0, 'long', 'payload', 0, False, 3)
        plugin.on_mqtt_publish(None, None, 3, None)
        plugin.shutdown()

        self.assertEqual([row['topic'] for row in self._rows()], ['long', 'long'])

    def test_missing_topics_disables_plugin(self):
        plugin, logger_queue = self._make_plugin(topics=None)

        self.assertEqual(plugin.get_callbacks(), [])
        log_messages = [call[0][0] for call in logger_queue.put.call_args_list]
        self.assertTrue(any(entry['log_type'] == 'ERROR' and 'topics' in entry['msg_text']
                            for entry in log_messages))

    def test_no_enabled_topics_disables_plugin(self):
        plugin, logger_queue = self._make_plugin(topics={'off': {'enable': False}})

        self.assertEqual(plugin.get_callbacks(), [])
        log_messages = [call[0][0] for call in logger_queue.put.call_args_list]
        self.assertTrue(any(entry['log_type'] == 'ERROR' for entry in log_messages))

    def test_unconfirmed_rows_are_not_pruned(self):
        plugin, logger_queue = self._make_plugin({'retention': 1, 'prune_interval': 1})
        plugin.mqtt_publish(None, 1, 0, 'topic', 'payload', 0, False, 1)
        plugin.shutdown()

        connection = weedb.connect(self.database_dict)
        try:
            plugin.tracker._prune(connection, time.time() + 10)  # pylint: disable=protected-access
        finally:
            connection.close()

        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'unconfirmed')
        log_messages = [call[0][0] for call in logger_queue.put.call_args_list]
        self.assertFalse(any(entry['log_type'] == 'ERROR' for entry in log_messages))

    def test_unconfirmed_retention_prunes_old_rows(self):
        plugin, _ = self._make_plugin({'unconfirmed_retention': 1, 'prune_interval': 3600})
        plugin.mqtt_publish(None, 1, 0, 'topic', 'payload', 0, False, 1)
        plugin.shutdown()

        connection = weedb.connect(self.database_dict)
        try:
            plugin.tracker._prune(connection, time.time() + 10)  # pylint: disable=protected-access
        finally:
            connection.close()

        self.assertEqual(self._rows(), [])

    def test_per_topic_unconfirmed_retention(self):
        plugin, _ = self._make_plugin(
            {'unconfirmed_retention': 3600, 'prune_interval': 3600},
            topics={'short': {'unconfirmed_retention': 1}, 'long': {}})
        plugin.mqtt_publish(None, 1, 0, 'short', 'payload', 0, False, 1)
        plugin.mqtt_publish(None, 2, 0, 'long', 'payload', 0, False, 2)
        plugin.shutdown()

        connection = weedb.connect(self.database_dict)
        try:
            plugin.tracker._prune(connection, time.time() + 10)  # pylint: disable=protected-access
        finally:
            connection.close()

        self.assertEqual([row['topic'] for row in self._rows()], ['long'])

    def test_sent_rows_are_not_pruned(self):
        plugin, _ = self._make_plugin({'retention': 1, 'prune_interval': 3600})
        plugin.mqtt_publish(None, 1, 0, 'topic', 'payload', 0, False, 1)
        rows = self._wait_for_rows(1)
        self.assertEqual(rows[0]['status'], 'sent')

        connection = weedb.connect(self.database_dict)
        try:
            plugin.tracker._prune(connection, time.time() + 10)  # pylint: disable=protected-access
        finally:
            connection.close()

        self.assertEqual(len(self._rows()), 1)
        plugin.shutdown()

    def test_other_rows_are_pruned(self):
        plugin, _ = self._make_plugin({'retention': 1, 'prune_interval': 1})
        plugin.mqtt_publish(None, 1, 1, 'topic', 'payload', 0, False, 1)  # a failed publish
        plugin.shutdown()

        connection = weedb.connect(self.database_dict)
        try:
            plugin.tracker._prune(connection, time.time() + 10)  # pylint: disable=protected-access
        finally:
            connection.close()

        self.assertEqual(self._rows(), [])

    def test_invalid_table_name_disables_plugin(self):
        plugin, logger_queue = self._make_plugin({'table': 'bad name'})

        self.assertEqual(plugin.get_callbacks(), [])
        log_messages = [call[0][0] for call in logger_queue.put.call_args_list]
        self.assertTrue(any(entry['log_type'] == 'ERROR' for entry in log_messages))

    def test_unknown_binding_disables_plugin(self):
        plugin, logger_queue = self._make_plugin({'data_binding': 'missing'})

        self.assertEqual(plugin.get_callbacks(), [])
        log_messages = [call[0][0] for call in logger_queue.put.call_args_list]
        self.assertTrue(any(entry['log_type'] == 'ERROR' for entry in log_messages))

    def test_missing_binding_disables_plugin(self):
        plugin, logger_queue = self._make_plugin(set_binding=False)

        self.assertEqual(plugin.get_callbacks(), [])
        log_messages = [call[0][0] for call in logger_queue.put.call_args_list]
        self.assertTrue(any(entry['log_type'] == 'ERROR' and 'data_binding' in entry['msg_text']
                            for entry in log_messages))

    def test_disabled_plugin_has_no_callbacks(self):
        plugin, _ = self._make_plugin({'enable': False})

        self.assertEqual(plugin.get_callbacks(), [])
        self.assertIsNone(plugin.tracker)

if __name__ == '__main__':
    helpers.run_tests()

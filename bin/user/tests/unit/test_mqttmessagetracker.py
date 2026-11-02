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

import helpers

import user.mqttmessagetracker
import weedb

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

    def _make_plugin(self, plugin_dict=None, set_binding=True):
        plugin_dict = dict(plugin_dict or {})
        if set_binding:
            plugin_dict.setdefault('data_binding', 'tracker_binding')

        logger_queue = mock.Mock()
        plugin = user.mqttmessagetracker.MQTTMessageTracker(logger_queue,
                                                            None,
                                                            'MQTTMessageTracker',
                                                            configobj.ConfigObj(plugin_dict),
                                                            None,
                                                            None,
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

    def test_get_callbacks(self):
        plugin, _ = self._make_plugin()

        callbacks = plugin.get_callbacks()

        self.assertEqual(callbacks[0]['mqtt_publish']['timing'], 'delay')
        self.assertEqual(callbacks[0]['mqtt_publish']['callback'], plugin.mqtt_publish)
        self.assertEqual(callbacks[1]['on_mqtt_publish']['timing'], 'immediate')
        self.assertEqual(callbacks[1]['on_mqtt_publish']['callback'], plugin.on_mqtt_publish)

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

    def test_shutdown_closes_unconfirmed_rows(self):
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

    def test_mid_reuse_closes_previous_row(self):
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

    def test_startup_closes_leftover_rows(self):
        plugin, _ = self._make_plugin()
        plugin.mqtt_publish(None, 1, 0, 'topic', 'payload', 0, False, 1)
        plugin.on_mqtt_publish(None, None, 1, None)
        plugin.shutdown()

        self._insert_sent_row(2, 'leftover')

        # A new tracker closes the rows the previous run left waiting for an arrival.
        self._make_plugin()

        rows = self._wait_for(lambda rows: all(row['status'] != 'sent' for row in rows))
        self.assertEqual(len(rows), 2)
        leftover = [row for row in rows if row['payload'] == 'leftover'][0]
        self.assertEqual(leftover['status'], 'unconfirmed')
        self.assertIsNotNone(leftover['unconfirmed_ts'])
        self.assertIsNone(leftover['arrived_ts'])

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

        time.sleep(1.1)
        plugin.mqtt_publish(None, 2, 0, 'new', 'payload', 0, False, 2)
        plugin.shutdown()

        rows = self._rows()
        self.assertEqual([row['mid'] for row in rows], [2])

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

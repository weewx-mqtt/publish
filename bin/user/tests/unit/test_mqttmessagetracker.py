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
        self.temp_dir = tempfile.TemporaryDirectory()
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
            cursor.execute(f"SELECT id, mid, dateTime, sent_ts, arrived_ts, topic, qos, retain, rc, payload "
                           f"FROM {table} ORDER BY mid")
            return cursor.fetchall()
        finally:
            connection.close()

    def _wait_for_rows(self, count, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if len(self._rows()) >= count:
                    return
            except weedb.DatabaseError:
                pass
            time.sleep(0.01)
        self.fail(f"The tracker did not write {count} rows.")

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
        self.assertEqual(len(row[0]), 32)
        self.assertEqual(row[1], 42)
        self.assertEqual(row[2], 123456)
        self.assertIsNotNone(row[3])
        self.assertIsNotNone(row[4])
        self.assertEqual(row[5], 'topic/one')
        self.assertEqual(row[6], 1)
        self.assertEqual(row[7], 0)
        self.assertEqual(row[8], 0)
        self.assertEqual(row[9], 'payload')

    def test_arrival_before_send(self):
        plugin, _ = self._make_plugin()

        plugin.on_mqtt_publish(None, None, 7, None)
        plugin.mqtt_publish(None, 7, 0, 'topic/two', 'payload', 0, True, 1)
        plugin.shutdown()

        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertIsNotNone(rows[0][4])

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

        self.assertEqual([row[9] for row in self._rows()], ['616263', '12.5', None])

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
        self.assertEqual([row[1] for row in rows], [2])

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

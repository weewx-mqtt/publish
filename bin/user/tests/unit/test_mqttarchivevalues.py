#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name

import unittest
import mock

import configobj

import helpers

import user.mqttarchivevalues

import weewx
import weewx.units

class Test_MQTTArchiveValues(unittest.TestCase):
    @staticmethod
    def _make_plugin(plugin_dict):
        logger_queue = mock.Mock()
        plugin_config = configobj.ConfigObj(plugin_dict)
        plugin = user.mqttarchivevalues.MQTTArchiveValues(logger_queue,
                                                          None,
                                                          helpers.random_string(),
                                                          plugin_config,
                                                          None,
                                                          None,
                                                          None)
        return plugin, logger_queue

    @staticmethod
    def _seed_archive(plugin, archive_data):
        plugin.on_weewx_data({'type': 'archive', 'data': archive_data})

    def test_init_disabled(self):
        plugin, logger_queue = self._make_plugin({'enable': False, 'topics': {'topic': {}}})

        self.assertFalse(plugin.enabled)
        self.assertEqual(logger_queue.put.call_count, 1)

    def test_get_callbacks(self):
        plugin, _ = self._make_plugin({'topics': {'topic': {}}})

        callbacks = plugin.get_callbacks()

        expected_callbacks = [
            {
                'on_weewx_data': {
                    'timing': 'immediate',
                    'callback': plugin.on_weewx_data
                },
                'update_record': {
                    'timing': 'delay',
                    'callback': plugin.update_record
                },
            },
        ]
        self.assertEqual(callbacks, expected_callbacks)

    def test_get_callbacks_disabled(self):
        plugin, _ = self._make_plugin({'enable': False, 'topics': {'topic': {}}})

        self.assertEqual(plugin.get_callbacks(), [])

    def test_on_weewx_data_archive(self):
        plugin, _ = self._make_plugin({'topics': {'topic': {}}})
        archive_data = {'dateTime': 1771939800, 'usUnits': weewx.METRIC, 'outTemp': 100}

        self._seed_archive(plugin, archive_data)

        self.assertEqual(plugin.archive_data, archive_data)

    def test_on_weewx_data_non_archive(self):
        plugin, _ = self._make_plugin({'topics': {'topic': {}}})

        plugin.on_weewx_data({'type': 'loop', 'data': {'outTemp': 100}})

        self.assertEqual(plugin.archive_data, {})

    def test_update_record_converts_units(self):
        topic = helpers.random_string()
        plugin, _ = self._make_plugin({'topics': {topic: {}}})
        self._seed_archive(plugin, {'usUnits': weewx.METRIC, 'outTemp': 100})

        record = {'usUnits': weewx.METRIC}
        plugin.update_record(None, topic, record, weewx.US, None, None)

        self.assertEqual(record['outTemp'], 212.0)

    def test_update_record_topic_not_configured(self):
        topic = helpers.random_string()
        plugin, _ = self._make_plugin({'topics': {topic: {}}})
        self._seed_archive(plugin, {'usUnits': weewx.METRIC, 'outTemp': 100})

        record = {'usUnits': weewx.METRIC}
        plugin.update_record(None, helpers.random_string(), record, weewx.US, None, None)

        self.assertNotIn('outTemp', record)

    def test_update_record_ignore_fields(self):
        topic = helpers.random_string()
        plugin, _ = self._make_plugin({'topics': {topic: {}}, 'ignore_fields': ['outTemp']})
        self._seed_archive(plugin, {'usUnits': weewx.METRIC, 'outTemp': 100, 'outHumidity': 50})

        record = {'usUnits': weewx.METRIC}
        plugin.update_record(None, topic, record, weewx.US, None, None)

        self.assertNotIn('outTemp', record)
        self.assertIn('outHumidity', record)

    def test_update_record_add_fields(self):
        topic = helpers.random_string()
        plugin, _ = self._make_plugin({'topics': {topic: {}}, 'add_fields': ['outHumidity']})
        self._seed_archive(plugin, {'usUnits': weewx.METRIC, 'outTemp': 100, 'outHumidity': 50})

        record = {'usUnits': weewx.METRIC}
        plugin.update_record(None, topic, record, weewx.US, None, None)

        self.assertNotIn('outTemp', record)
        self.assertIn('outHumidity', record)

    def test_update_record_none_value(self):
        topic = helpers.random_string()
        plugin, _ = self._make_plugin({'topics': {topic: {}}})
        self._seed_archive(plugin, {'usUnits': weewx.METRIC, 'outTemp': None})

        record = {'usUnits': weewx.METRIC}
        plugin.update_record(None, topic, record, weewx.US, None, None)

        self.assertNotIn('outTemp', record)

    def test_update_record_existing_value_not_overwritten(self):
        topic = helpers.random_string()
        plugin, _ = self._make_plugin({'topics': {topic: {}}})
        self._seed_archive(plugin, {'usUnits': weewx.METRIC, 'outTemp': 100})

        record = {'usUnits': weewx.METRIC, 'outTemp': 999}
        plugin.update_record(None, topic, record, weewx.US, None, None)

        self.assertEqual(record['outTemp'], 999)

    def test_update_record_no_archive_data(self):
        topic = helpers.random_string()
        plugin, _ = self._make_plugin({'topics': {topic: {}}})

        record = {'usUnits': weewx.METRIC}
        plugin.update_record(None, topic, record, weewx.US, None, None)

        self.assertEqual(record, {'usUnits': weewx.METRIC})

if __name__ == '__main__':
    helpers.run_tests()

#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name
import unittest
import mock

import helpers

import user.mqttpublish

class StubPlugin():
    """ Stand in for a user plugin. """
    def __init__(self, logger_queue, monitor_config, name, plugin_dict, mqtt_dict, topics, weewx_dict):
        self.constructor_args = (logger_queue, monitor_config, name, plugin_dict, mqtt_dict, topics, weewx_dict)
        self.callback = mock.Mock()
        self.shutdown = mock.Mock()

    def get_callbacks(self):
        return [{'on_weewx_data': {'timing': 'immediate', 'callback': self.callback}},
                {'on_mqtt_publish': {'timing': 'immediate', 'callback': self.callback}},
                {'update_record': {'timing': 'delay', 'callback': self.callback}}]

class StubPluginWithoutShutdown():
    """ Stand in for a user plugin that does not need to shut down. """
    def __init__(self, logger_queue, monitor_config, name, plugin_dict, mqtt_dict, topics, weewx_dict):
        self.constructor_args = (logger_queue, monitor_config, name, plugin_dict, mqtt_dict, topics, weewx_dict)
        self.callback = mock.Mock()

    def get_callbacks(self):
        return [{'on_weewx_data': {'timing': 'immediate', 'callback': self.callback}}]

class TestPluginManager(unittest.TestCase):
    def test_create_plugin(self):
        logger = mock.Mock()
        monitor_config = {helpers.random_string(): helpers.random_string()}
        plugin_dict = {helpers.random_string(): helpers.random_string()}
        mqtt_dict = {helpers.random_string(): helpers.random_string()}
        topics = {helpers.random_string(): helpers.random_string()}
        weewx_dict = {helpers.random_string(): helpers.random_string()}

        SUT = user.mqttpublish.PluginManager(logger, monitor_config, mqtt_dict, topics, weewx_dict)

        name = helpers.random_string()
        plugin_name = helpers.random_string()

        with mock.patch('weeutil.weeutil.get_object', return_value=StubPlugin) as mock_get_object:
            SUT.create_plugin(name, plugin_name, plugin_dict)

        mock_get_object.assert_called_once_with(plugin_name)

        plugin = SUT.plugins[name]['plugin']
        self.assertIsInstance(plugin, StubPlugin)
        self.assertEqual(plugin.constructor_args,
                         (logger, monitor_config, plugin_name, plugin_dict, mqtt_dict, topics, weewx_dict))

    def test_create_plugin_registers_callbacks(self):
        SUT = user.mqttpublish.PluginManager(mock.Mock(), {}, {}, {}, {})

        name = helpers.random_string()

        with mock.patch('weeutil.weeutil.get_object', return_value=StubPlugin):
            SUT.create_plugin(name, helpers.random_string(), {})

        callback = SUT.plugins[name]['plugin'].callback
        self.assertIs(SUT.callbacks['on_weewx_data']['immediate'][name], callback)
        self.assertIs(SUT.callbacks['on_mqtt_publish']['immediate'][name], callback)
        self.assertIs(SUT.callbacks['update_record']['delay'][name], callback)

    def test_shutdown_calls_plugin_shutdown(self):
        SUT = user.mqttpublish.PluginManager(mock.Mock(), {}, {}, {}, {})

        first = StubPlugin(None, None, None, None, None, None, None)
        second = StubPlugin(None, None, None, None, None, None, None)
        SUT.plugins = {'first': {'plugin': first}, 'second': {'plugin': second}}

        SUT.shutdown()

        first.shutdown.assert_called_once_with()
        second.shutdown.assert_called_once_with()

    def test_shutdown_skips_plugins_without_shutdown(self):
        mock_logger_queue = mock.Mock()
        SUT = user.mqttpublish.PluginManager(mock_logger_queue, {}, {}, {}, {})

        plugin = StubPluginWithoutShutdown(None, None, None, None, None, None, None)
        SUT.plugins = {'plain': {'plugin': plugin}, 'unfinished': {}}

        SUT.shutdown()

        mock_logger_queue.put.assert_not_called()

    def test_shutdown_logs_error_and_continues(self):
        mock_logger_queue = mock.Mock()
        SUT = user.mqttpublish.PluginManager(mock_logger_queue, {}, {}, {}, {})

        bad_plugin = mock.Mock()
        bad_plugin.shutdown.side_effect = ValueError('boom')
        good_plugin = mock.Mock()
        SUT.plugins = {'bad': {'plugin': bad_plugin}, 'good': {'plugin': good_plugin}}

        SUT.shutdown()

        good_plugin.shutdown.assert_called_once_with()

        log_entry = mock_logger_queue.put.call_args[0][0]
        self.assertEqual(log_entry['log_type'], 'ERROR')
        self.assertIn('bad', log_entry['msg_text'])
        self.assertIn('boom', log_entry['msg_text'])

if __name__ == '__main__':
    helpers.run_tests()

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

import user.mqtthaconfig

class test_MQTTHomeAssistantConfig(unittest.TestCase):
    def test_get_callbacks(self):
        mock_logger = mock.Mock()
        name = helpers.random_string()
        plugin_dict = {
            'devices': {},
            'component_data': {}
        }
        weewx_dict = {
            'defaults': {}
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger, name, configobj.ConfigObj(plugin_dict), weewx_dict)

        callbacks = SUT.get_callbacks()

        expected_callbacks = [
            {
                'on_mqtt_connect': {
                    'timing': 'immediate',
                    'callback': SUT.on_mqtt_connect
                }
            },
            {
                'on_mqtt_message': {
                    'timing': 'immediate',
                    'callback': SUT.on_mqtt_message
                },
                'update_record': {
                    'timing': 'delay',
                    'callback': SUT.update_record
                },
            },
        ]
        self.assertEqual(callbacks, expected_callbacks)

if __name__ == '__main__':
    helpers.run_tests()

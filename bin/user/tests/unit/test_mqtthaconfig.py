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
from io import StringIO

import helpers

import user.mqtthaconfig

class test_MQTTHomeAssistantConfig(unittest.TestCase):
    @unittest.skip("placeholder")
    def test_init(self):
        mock_logger = mock.Mock()
        name = helpers.random_string()
        plugin_dict = {
            'devices': {
                helpers.random_string(): {
                    'topics': {
                        helpers.random_string(): {},
                    },
                },
            },
        }
        weewx_dict = {
            'defaults': {}
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger, name, configobj.ConfigObj(plugin_dict), weewx_dict)

        print(SUT.mqtt_config)
        print(SUT.configuration)
        print(SUT.defaults)
        print(SUT.state_topics)
        print("done")

    def test_init_component_data(self):
        mock_logger = mock.Mock()
        name = helpers.random_string()
        compoennt_key = helpers.random_string()
        component_value = helpers.random_string()
        plugin_dict = {
            'devices': {
                helpers.random_string(): {
                    'topics': {
                        helpers.random_string(): {},
                    },
                },
            },
            'component_data': {
                compoennt_key: component_value,
            },
        }
        weewx_dict = {
            'defaults': {}
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger, name, configobj.ConfigObj(plugin_dict), weewx_dict)

        expected_defaults = configobj.ConfigObj(StringIO(user.mqtthaconfig.DEFAULTS_STR))
        expected_defaults['component_data'][compoennt_key] = component_value

        print(SUT.defaults)
        print(expected_defaults)

        self.assertDictEqual(SUT.defaults, expected_defaults)

        print("done")

    def test_init_configuration(self):
        mock_logger = mock.Mock()
        name = helpers.random_string()
        device_id = helpers.random_string()
        origin_name = helpers.random_string()
        device_name = helpers.random_string()
        device_key = helpers.random_string()
        device_value = helpers.random_string()
        origin_key = helpers.random_string()
        origin_value = helpers.random_string()
        plugin_dict = {
            'devices': {
                device_id: {
                    'topics': {
                        helpers.random_string(): {},
                    },
                    'device': {
                        'name': device_name,
                        device_key: device_value,
                    },
                    'origin': {
                        'name': origin_name,
                        origin_key: origin_value
                    },
                },
            },
        }
        weewx_dict = {
            'defaults': {}
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger, name, configobj.ConfigObj(plugin_dict), weewx_dict)

        expected_config = {
            'devices': {
                device_id: {
                    'availability_topic': 'status',
                    'components': {},
                    'origin': {
                        origin_key: origin_value,
                        'name': origin_name,
                    },
                    'device': {
                        'name': device_name,
                        'identifiers': device_id,
                        device_key: device_value,
                    },
                }
            }
        }

        self.assertDictEqual(SUT.configuration.dict(), expected_config)

    def test_get_callbacks(self):
        mock_logger = mock.Mock()
        name = helpers.random_string()
        plugin_dict = {
            'devices': {
                helpers.random_string(): {
                    'topics': {
                        helpers.random_string(): {},
                    },
                }
            },
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

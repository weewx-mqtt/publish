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
import random

import helpers
import mqttstubs

import user.mqtthaconfig

class test_MQTTHomeAssistantConfig(unittest.TestCase):
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
        print(SUT)
        print("done")

    def test_init_mqtt_config(self):
        mock_logger = mock.Mock()
        name = helpers.random_string()
        device_id = helpers.random_string()
        qos = random.randint(0, 2)
        ignore_fields = helpers.random_string()
        plugin_dict = {
            'devices': {
                device_id: {
                    'qos': qos,
                    'ignore_fields': ignore_fields,
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
        expected_results = {
            device_id: {
                'ignore_none_value': True,
                'ignore_fields': [ignore_fields],
                'qos': qos,
                'retain': False,
            },
        }

        self.assertDictEqual(SUT.mqtt_config, expected_results)

    def test_init_state_topics(self):
        mock_logger = mock.Mock()
        name = helpers.random_string()
        device_id = helpers.random_string()
        topic = helpers.random_string()
        plugin_dict = {
            'devices': {
                device_id: {
                    'topics': {
                        topic: {},
                    },
                },
            },
        }
        weewx_dict = {
            'defaults': {}
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger, name, configobj.ConfigObj(plugin_dict), weewx_dict)

        expected_result = {
            device_id: {
                topic: {
                    'type': 'json'
                },
            },
        }

        self.assertDictEqual(SUT.state_topics, expected_result)

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

        expected_result = configobj.ConfigObj(StringIO(user.mqtthaconfig.DEFAULTS_STR))
        expected_result['component_data'][compoennt_key] = component_value

        self.assertDictEqual(SUT.defaults, expected_result)

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

        expected_result = {
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

        self.assertDictEqual(SUT.configuration.dict(), expected_result)

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

    def test_received_birth_message(self):
        mock_client = mock.Mock()
        mock_logger = mock.Mock()
        name = helpers.random_string()
        device_id = helpers.random_string()
        plugin_dict = {
            'devices': {
                device_id: {
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

        qos = 0
        retain = False
        msg = mqttstubs.Msg('homeassistant/status', b'online', qos, retain)
        SUT.on_mqtt_message(mock_client, None, msg)

        topic = f'homeassistant/device/{device_id}/config'
        payload = f'{{"availability_topic": "status", "components": {{}}, "origin": {{"name": "WeeWX"}}, "device": {{"identifiers": "{device_id}", "name": "{device_id}"}}}}'

        mock_client.publish.assert_called_once_with(topic, payload, qos=qos, retain=retain)

    def test_received_lwt_message(self):
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

        msg = mqttstubs.Msg('homeassistant/status', b'offline', 0, False)
        SUT.on_mqtt_message(mock.Mock(), None, msg)

        mock_logger.loginf.assert_called_once_with("Received LWT b'offline' on topic: homeassistant/status.")

    def test_unknown_message(self):
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

        msg = mqttstubs.Msg('homeassistant/status', b'unknown', 0, False)
        SUT.on_mqtt_message(mock.Mock(), None, msg)

        mock_logger.logerr.assert_called_once_with("Received invalid b'unknown' on topic: homeassistant/status.")

    def test_on_connection(self):
        mock_client = mock.Mock()
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

        mock_client.subscribe.return_value = (random.randint(0, 99), random.randint(0, 99))
        SUT.on_mqtt_connect(mock_client, None, None, None, None)

        self.assertEqual(mock_client.subscribe.call_count, 2)

    def test_init00(self):
        mock_logger = mock.Mock()
        name = helpers.random_string()
        device_id = helpers.random_string()
        state_topic = helpers.random_string()
        plugin_dict = {
            'devices': {
                device_id: {
                    'topics': {
                        state_topic: {},
                    },
                },
            },
        }
        weewx_dict = {
            'defaults': {
                'Labels': {
                    'Generic': {},
                },
            },
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger, name, configobj.ConfigObj(plugin_dict), weewx_dict)

        with mock.patch.object(user.mqtthaconfig.weewx.units,
                               'getStandardUnitType',
                               side_effect=[(helpers.random_string(), helpers.random_string()),
                                            ('inch', helpers.random_string())]):
            record = {
                'usUnits': 'foobar',
                'rain': random.random()
            }

            mock_client = mock.Mock()

            SUT.update_record(mock_client, state_topic, record, None, None)

            topic = f'homeassistant/device/{device_id}/config'
            payload = (
                '{"availability_topic": "status", "components": {"usUnits": {"state_topic": '
                f'"{state_topic}", "platform": "sensor", "value_template": '
                '"{{ value_json.usUnits | default(this.state) }}", "unique_id": "usUnits", "name": "usUnits", "class": "enum"}, '
                '"rain": {"state_topic": '
                f'"{state_topic}", "platform": "sensor", "value_template": '
                '"{{ value_json.rain | default(this.state) }}", "unique_id": "rain", "name": "rain", "unit_of_measurement": "in", '
                '"device_class": "precipitation", "state_class": "total", "class": "precipitation"}}, '
                '"origin": {"name": "WeeWX"}, "device": {"identifiers": '
                f'"{device_id}", "name": "{device_id}"'
                '}}'
            )

            mock_client.publish.assert_called_once_with(topic, payload, qos=0, retain=False)

if __name__ == '__main__':
    helpers.run_tests()

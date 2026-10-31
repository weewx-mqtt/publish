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
import havalid
import mqttstubs

import user.mqtthaconfig

import weewx.units

def invalid_component_classes(component_data):
    """ Return a list of error strings, one per component entry with a
        device_class or state_class that Home Assistant does not accept.
        An empty list means every entry is valid. """
    errors = []
    for component in component_data.sections:
        device_class = component_data[component].get('device_class')
        if device_class is not None and device_class not in havalid.VALID_DEVICE_CLASSES:
            errors.append(f"[{component}] device_class '{device_class}' is not a valid "
                          f"Home Assistant device class")

        state_class = component_data[component].get('state_class')
        if state_class is not None and state_class not in havalid.VALID_STATE_CLASSES:
            errors.append(f"[{component}] state_class '{state_class}' is not a valid "
                          f"Home Assistant state class")
    return errors

class test_MQTTHomeAssistantConfig(unittest.TestCase):
    def test_init(self):
        mock_logger_queue = mock.Mock()
        name = helpers.random_string()
        topics = {
            helpers.random_string(): {
                'type': helpers.random_string(),
            },
        }
        plugin_dict = {
            'devices': {
                helpers.random_string(): {
                    'topics': topics,
                },
            },
        }
        weewx_dict = {
            'defaults': {}
        }

        user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger_queue,
                                                  None,
                                                  name,
                                                  configobj.ConfigObj(plugin_dict),
                                                  {},
                                                  topics, weewx_dict)

    def test_init_mqtt_config(self):
        mock_logger_queue = mock.Mock()
        name = helpers.random_string()
        device_id = helpers.random_string()
        qos = random.randint(0, 2)
        ignore_fields = helpers.random_string()
        topics = {
            helpers.random_string(): {
                'type': helpers.random_string(),
            },
        }
        plugin_dict = {
            'devices': {
                device_id: {
                    'qos': qos,
                    'ignore_fields': ignore_fields,
                    'topics': topics,
                },
            },
        }
        weewx_dict = {
            'defaults': {}
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger_queue,
                                                        None,
                                                        name,
                                                        configobj.ConfigObj(plugin_dict),
                                                        {},
                                                        topics,
                                                        weewx_dict)
        expected_results = {
            device_id: {
                'ignore_fields': [ignore_fields],
                'qos': qos,
                'retain': False,
            },
        }

        self.assertDictEqual(SUT.mqtt_config, expected_results)

    def test_init_state_topics(self):
        mock_logger_queue = mock.Mock()
        name = helpers.random_string()
        device_id = helpers.random_string()
        topic = helpers.random_string()
        topic_type = helpers.random_string()
        topics = {
            topic: {
                'type': topic_type,
            },
        }
        plugin_dict = {
            'devices': {
                device_id: {
                    'topics': topics,
                },
            },
        }
        weewx_dict = {
            'defaults': {}
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger_queue,
                                                        None,
                                                        name,
                                                        configobj.ConfigObj(plugin_dict),
                                                        {},
                                                        topics,
                                                        weewx_dict)

        expected_result = {
            device_id: {
                topic: {
                    'type': topic_type
                },
            },
        }

        self.assertDictEqual(SUT.state_topics, expected_result)

    def test_init_component_data(self):
        mock_logger_queue = mock.Mock()
        name = helpers.random_string()
        component_key = helpers.random_string()
        component_value = helpers.random_string()
        device_id = helpers.random_string()
        topics = {
            helpers.random_string(): {
                'type': helpers.random_string(),
            },
        }
        plugin_dict = {
            'devices': {
                device_id: {
                    'topics': topics,
                },
            },
            'component_data': {
                component_key: component_value,
            },
        }
        weewx_dict = {
            'defaults': {}
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger_queue,
                                                        None,
                                                        name,
                                                        configobj.ConfigObj(plugin_dict),
                                                        {},
                                                        topics,
                                                        weewx_dict)

        expected_result = {}
        expected_result['units'] = configobj.ConfigObj(StringIO(user.mqtthaconfig.DEFAULT_UNITS))
        expected_result['component_data'] = {}
        expected_result['component_data'][device_id] = configobj.ConfigObj(StringIO(user.mqtthaconfig.DEFAULT_COMPONENT_DATA))
        expected_result['component_data'][device_id][component_key] = component_value

        self.assertDictEqual(SUT.defaults, expected_result)

    def test_default_units_are_valid_weewx_units(self):
        weewx_units = set(weewx.units.USUnits.values())
        weewx_units.update(weewx.units.MetricUnits.values())
        weewx_units.update(weewx.units.MetricWXUnits.values())
        weewx_units.update(weewx.units.conversionDict)
        for conversions in weewx.units.conversionDict.values():
            weewx_units.update(conversions)

        units = configobj.ConfigObj(StringIO(user.mqtthaconfig.DEFAULT_UNITS))
        for unit in units.keys():
            self.assertIn(unit, weewx_units, f"{unit} is not a valid weewx unit")

    def test_default_component_data_classes(self):
        component_data = configobj.ConfigObj(StringIO(user.mqtthaconfig.DEFAULT_COMPONENT_DATA))

        self.assertEqual(invalid_component_classes(component_data), [])

    def test_init_configuration(self):
        mock_logger_queue = mock.Mock()
        name = helpers.random_string()
        device_id = helpers.random_string()
        origin_name = helpers.random_string()
        device_name = helpers.random_string()
        device_key = helpers.random_string()
        device_value = helpers.random_string()
        origin_key = helpers.random_string()
        origin_value = helpers.random_string()
        topics = {
            helpers.random_string(): {
                'type': helpers.random_string(),
            },
        }
        plugin_dict = {
            'devices': {
                device_id: {
                    'topics': topics,
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

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger_queue,
                                                        None,
                                                        name,
                                                        configobj.ConfigObj(plugin_dict),
                                                        {},
                                                        topics,
                                                        weewx_dict)

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
        mock_logger_queue = mock.Mock()
        name = helpers.random_string()
        topics = {
            helpers.random_string(): {
                'type': helpers.random_string(),
            }
        }
        plugin_dict = {
            'devices': {
                helpers.random_string(): {
                    'topics': topics,
                }
            },
        }
        weewx_dict = {
            'defaults': {}
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger_queue,
                                                        None,
                                                        name,
                                                        configobj.ConfigObj(plugin_dict),
                                                        {},
                                                        topics,
                                                        weewx_dict)

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
        mock_logger_queue = mock.Mock()
        name = helpers.random_string()
        device_id = helpers.random_string()
        topics = {
            helpers.random_string(): {
                'type': helpers.random_string(),
            },
        }
        plugin_dict = {
            'devices': {
                device_id: {
                    'topics': topics,
                },
            },
        }
        weewx_dict = {
            'defaults': {}
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger_queue,
                                                        None,
                                                        name,
                                                        configobj.ConfigObj(plugin_dict),
                                                        {},
                                                        topics,
                                                        weewx_dict)

        qos = 0
        retain = False
        msg = mqttstubs.Msg('homeassistant/status', b'online', qos, retain)
        SUT.on_mqtt_message(mock_client, None, msg)

        topic = f'homeassistant/device/{device_id}/config'
        payload = (f'{{"availability_topic": "status", "components": {{}}, "origin": {{"name": "WeeWX"}}, '
                   f'"device": {{"identifiers": "{device_id}", "name": "{device_id}"}}}}')

        mock_client.publish.assert_called_once_with(topic, payload, qos=qos, retain=retain)

    def test_received_lwt_message(self):
        mock_logger_queue = mock.Mock()
        name = helpers.random_string()
        topics = {
            helpers.random_string(): {
                'type': helpers.random_string(),
            },
        }
        plugin_dict = {
            'devices': {
                helpers.random_string(): {
                    'topics': topics,
                },
            },
        }
        weewx_dict = {
            'defaults': {}
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger_queue,
                                                        None,
                                                        name,
                                                        configobj.ConfigObj(plugin_dict),
                                                        {},
                                                        topics,
                                                        weewx_dict)

        msg = mqttstubs.Msg('homeassistant/status', b'offline', 0, False)

        mock_logger_queue.reset_mock()
        SUT.on_mqtt_message(mock.Mock(), None, msg)

        self.assertEqual(mock_logger_queue.put.call_count, 2)

    def test_unknown_message(self):
        mock_logger_queue = mock.Mock()
        name = helpers.random_string()
        topics = {
            helpers.random_string(): {
                'type': helpers.random_string(),
            },
        }
        plugin_dict = {
            'devices': {
                helpers.random_string(): {
                    'topics': topics,
                },
            },
        }
        weewx_dict = {
            'defaults': {}
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger_queue,
                                                        None,
                                                        name,
                                                        configobj.ConfigObj(plugin_dict),
                                                        {},
                                                        topics,
                                                        weewx_dict)

        msg = mqttstubs.Msg('homeassistant/status', b'unknown', 0, False)
        SUT.on_mqtt_message(mock.Mock(), None, msg)

        self.assertEqual(mock_logger_queue.put.call_count, 3)

    def test_on_connection(self):
        mock_client = mock.Mock()
        mock_logger_queue = mock.Mock()
        name = helpers.random_string()
        topics = {
            helpers.random_string(): {
                'type': helpers.random_string(),
            },
        }
        plugin_dict = {
            'devices': {
                helpers.random_string(): {
                    'topics': topics,
                },
            },
        }
        weewx_dict = {
            'defaults': {}
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger_queue,
                                                        None,
                                                        name,
                                                        configobj.ConfigObj(plugin_dict),
                                                        {},
                                                        topics,
                                                        weewx_dict)

        mock_client.subscribe.return_value = (random.randint(0, 99), random.randint(0, 99))
        SUT.on_mqtt_connect(mock_client, None, None, None, None)

        self.assertEqual(mock_client.subscribe.call_count, 2)

    def test_update_record(self):
        mock_logger_queue = mock.Mock()
        name = helpers.random_string()
        device_id = helpers.random_string()
        state_topic = helpers.random_string()
        topics = {
            state_topic: {
                'type': helpers.random_string(),
                'fields': {},
            }
        }
        plugin_dict = {
            'devices': {
                device_id: {
                    'topics': topics,
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

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger_queue,
                                                        None,
                                                        name,
                                                        configobj.ConfigObj(plugin_dict),
                                                        {},
                                                        topics,
                                                        weewx_dict)

        with mock.patch.object(user.mqtthaconfig.weewx.units,
                               'getStandardUnitType',
                               side_effect=[(helpers.random_string(), helpers.random_string()),
                                            ('inch', helpers.random_string())]):
            record = {
                'usUnits': random.randint(0, 99),
                'rain': random.random()
            }

            mock_client = mock.Mock()

            SUT.update_record(mock_client, state_topic, record, None, None, None)

            topic = f'homeassistant/device/{device_id}/config'
            payload = (
                '{"availability_topic": "status", "components": {"usUnits": {"state_topic": '
                f'"{state_topic}", "platform": "sensor", "value_template": '
                '"{{ value_json.usUnits | default(this.state) }}", '
                f'"unique_id": "{device_id}_usUnits", '
                '"name": "usUnits", "device_class": "enum", "options": ["1", "16", "17"]}, '
                '"rain": {"state_topic": '
                f'"{state_topic}", "platform": "sensor", "value_template": '
                '"{{ value_json.rain | default(this.state) }}", '
                f'"unique_id": "{device_id}_rain", '
                '"name": "rain", "unit_of_measurement": "in", '
                '"device_class": "precipitation", "state_class": "total"}}, '
                '"origin": {"name": "WeeWX"}, "device": {"identifiers": '
                f'"{device_id}", "name": "{device_id}"'
                '}}'
            )

            mock_client.publish.assert_called_once_with(topic, payload, qos=0, retain=False)

    def test_init_device_enable_true(self):
        mock_logger_queue = mock.Mock()
        name = helpers.random_string()
        device_id = helpers.random_string()
        topic = helpers.random_string()
        topics = {
            topic: {
                'type': helpers.random_string(),
            },
        }
        plugin_dict = {
            'devices': {
                device_id: {
                    'enable': 'true',
                    'topics': topics,
                },
            },
        }
        weewx_dict = {
            'defaults': {}
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger_queue,
                                                        None,
                                                        name,
                                                        configobj.ConfigObj(plugin_dict),
                                                        {},
                                                        topics,
                                                        weewx_dict)

        expected_result = {
            device_id: {
                topic: {
                    'type': topics[topic]['type'],
                },
            },
        }

        self.assertDictEqual(SUT.state_topics, expected_result)
        self.assertIn(device_id, SUT.configuration['devices'])

    def test_init_device_enable_false(self):
        mock_logger_queue = mock.Mock()
        name = helpers.random_string()
        device_id = helpers.random_string()
        topics = {
            helpers.random_string(): {
                'type': helpers.random_string(),
            },
        }
        plugin_dict = {
            'devices': {
                device_id: {
                    'enable': 'false',
                    'topics': topics,
                },
            },
        }
        weewx_dict = {
            'defaults': {}
        }

        SUT = user.mqtthaconfig.MQTTHomeAssistantConfig(mock_logger_queue,
                                                        None,
                                                        name,
                                                        configobj.ConfigObj(plugin_dict),
                                                        {},
                                                        topics,
                                                        weewx_dict)

        self.assertDictEqual(SUT.state_topics, {})
        self.assertDictEqual(SUT.configuration['devices'], {})

if __name__ == '__main__':
    helpers.run_tests()

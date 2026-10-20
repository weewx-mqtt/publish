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

import configobj
import random

import paho.mqtt

import user.mqttcommon
import user.mqttpublish
import mqttstubs

class TestPublisher(unittest.TestCase):
    @staticmethod
    def _create(config_dict, api=None):
        config = configobj.ConfigObj(config_dict)
        monitor_dict = {
            'monitor_on_message': None,
            'monitor_on_connect': None,
        }

        with mock.patch.object(user.mqttpublish.Publisher, 'get_client', return_value=mock.Mock()):
            with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                return user.mqttpublish.Publisher(mock.Mock(), None, mock.Mock(), config, monitor_dict, api=api)

    def test_api_default_for_paho_mqtt_v1(self):
        config_dict = {
            'protocol': getattr(paho.mqtt.client, 'MQTTv311', 0),
            'clientid': helpers.random_string(),
            'log_mqtt': False,
            'username': None,
            'password': None,
        }

        with mqttstubs.patch_delattr(user.mqttpublish.mqtt, 'CallbackAPIVersion'):
            SUT = self._create(config_dict)

        self.assertEqual(SUT.api, user.mqttcommon.API_V1)

    def test_api_default_for_paho_mqtt_v2(self):
        protocol_string = 'MQTTv5'

        config_dict = {
            'protocol': getattr(paho.mqtt.client, protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': False,
            'username': None,
            'password': None,
        }

        with mqttstubs.patch_addattr(user.mqttpublish.mqtt, 'CallbackAPIVersion'):
            SUT = self._create(config_dict)

        self.assertEqual(SUT.api, user.mqttcommon.API_V2_MQTT5)

    def test_api_default_for_paho_mqtt_v2_mqtt_v3(self):
        protocol_string = random.choice(['MQTTv31', 'MQTTv311'])

        config_dict = {
            'protocol': getattr(paho.mqtt.client, protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': False,
            'username': None,
            'password': None,
        }

        with mqttstubs.patch_addattr(user.mqttpublish.mqtt, 'CallbackAPIVersion'):
            SUT = self._create(config_dict)

        self.assertEqual(SUT.api, user.mqttcommon.API_V2_MQTT3)

    def test_invalid_protocol_for_paho_mqtt_v1_api(self):
        config_dict = {
            'protocol': getattr(paho.mqtt.client, 'MQTTv5', 0),
        }

        with self.assertRaisesRegex(ValueError, 'Invalid protocol'):
            self._create(config_dict, api=user.mqttcommon.API_V1)

if __name__ == '__main__':
    helpers.run_tests()

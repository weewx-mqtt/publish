#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name

import configobj
import paho.mqtt
import random

import unittest
import mock

import helpers
import mqttstubs

import user.mqttpublish

# @unittest.skipIf(hasattr(paho.mqtt.client, 'CallbackAPIVersion'), "paho-mqtt is NOT v1, skipping tests.")
class PublisherBase(unittest.TestCase):
    class_under_test = object
    protocol_string = None

    def test_username_set(self):
        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': helpers.random_string(),
            'password': None,
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'max_retries': 0,
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'username_pw_set') as mock_username_pw_set:

                        self.class_under_test(mock_logger, mock_publisher, config)

                        mock_username_pw_set.assert_not_called()

    def test_password_set(self):
        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': None,
            'password': helpers.random_string(),
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'max_retries': 0,
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'username_pw_set') as mock_username_pw_set:

                        self.class_under_test(mock_logger, mock_publisher, config)

                        mock_username_pw_set.assert_not_called()

    def test_username_password_set(self):
        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': helpers.random_string(),
            'password': helpers.random_string(),
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'max_retries': 0,
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'username_pw_set') as mock_username_pw_set:

                        self.class_under_test(mock_logger, mock_publisher, config)

                        mock_username_pw_set.assert_called_once_with(config_dict['username'], config_dict['password'])

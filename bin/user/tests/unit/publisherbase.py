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

    def test_get_client(self):
        raise NotImplementedError("test 'test_get_client' is not implemented")

    def test_set_callbacks(self):
        # pylint: disable=no-member

        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': False,
            'username': None,
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

                    SUT = self.class_under_test(mock_logger, mock_publisher, config)

                    self.assertNotEqual(SUT.client.on_log, SUT.on_log)
                    self.assertEqual(SUT.client.on_connect, SUT.on_connect)
                    self.assertEqual(SUT.client.on_disconnect, SUT.on_disconnect)
                    self.assertEqual(SUT.client.on_publish, SUT.on_publish)

    def test_set_on_log_callback(self):
        # pylint: disable=no-member

        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': True,
            'username': None,
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

                    SUT = self.class_under_test(mock_logger, mock_publisher, config)

                    self.assertEqual(SUT.client.on_log, SUT.on_log)
                    self.assertEqual(SUT.client.on_connect, SUT.on_connect)
                    self.assertEqual(SUT.client.on_disconnect, SUT.on_disconnect)
                    self.assertEqual(SUT.client.on_publish, SUT.on_publish)

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

    def test_test(self):
        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': None,
            'password': None,
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'max_retries': random.choice[0, 2],
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.mqtt.Client,
                                       'connect',
                                       side_effect=mqttstubs.ClientStub.connect_without_connection,
                                       autospec=True) as mock_connect:

                    self.class_under_test(mock_logger, mock_publisher, config)

                    self.assertEqual(mock_connect.call_count, config_dict['max_retries'] + 1)

        print("done")

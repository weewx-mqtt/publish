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
import ssl

import unittest
import mock

import helpers
import mqttstubs

import user.mqttpublish

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

    def test_connect_connection(self):
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
            'max_retries': random.choice([0, 2]),
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.mqtt.Client,
                                       'connect',
                                       side_effect=mqttstubs.ClientStub.connect_with_connection,
                                       autospec=True) as mock_connect:

                    self.class_under_test(mock_logger, mock_publisher, config)

                    self.assertEqual(mock_connect.call_count, 1)

    def test_connect_no_connection(self):
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
            'max_retries': random.choice([0, 2]),
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

    def test_connect_first_call_exception(self):
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
            'max_retries': random.choice([0, 2]),
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.mqtt.Client,
                                       'connect',
                                       side_effect=mqttstubs.ClientStub.connect_exception_first_call,
                                       autospec=True) as mock_connect:

                    self.class_under_test(mock_logger, mock_publisher, config)

                    self.assertEqual(mock_connect.call_count, config_dict['max_retries'] + 1)
                    self.assertEqual(mock_logger.logerr.call_count, 2)

    def test_connect_subsequent_call_exception(self):
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
            'max_retries': random.choice([1, 2]),
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.mqtt.Client,
                                       'connect',
                                       side_effect=mqttstubs.ClientStub.connect_exception_subsequent_calls,
                                       autospec=True) as mock_connect:

                    self.class_under_test(mock_logger, mock_publisher, config)

                    self.assertEqual(mock_connect.call_count, config_dict['max_retries'] + 1)
                    self.assertEqual(mock_logger.logerr.call_count, config_dict['max_retries'] * 2)

    def test_will_set_with_defaults(self):
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
            'max_retries': random.randint(0, 10),
            'lwt': {
                'enable': True,
            }
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'will_set') as mock_will_set:

                        self.class_under_test(mock_logger, mock_publisher, config)

                        mock_will_set.assert_called_once_with(topic='status', payload='offline', qos=0, retain=True)

    def test_will_set_with_configured_values(self):
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
            'max_retries': random.randint(0, 10),
            'lwt': {
                'enable': True,
                'topic': helpers.random_string(),
                'offline_payload': helpers.random_string(),
                'qos': random.randint(1, 5),
                'retain': False,
            }
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'will_set') as mock_will_set:

                        self.class_under_test(mock_logger, mock_publisher, config)

                        mock_will_set.assert_called_once_with(topic=config_dict['lwt']['topic'],
                                                              payload=config_dict['lwt']['offline_payload'],
                                                              qos=config_dict['lwt']['qos'],
                                                              retain=config_dict['lwt']['retain'])

    def test_publish_when_connected(self):
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
            'max_retries': random.randint(0, 10),
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.AbstractPublisher, '_reconnect') as mock_reconnect:
                        with mock.patch.object(user.mqttpublish.mqtt.Client, 'publish') as mock_publish:

                            SUT = self.class_under_test(mock_logger, mock_publisher, config)

                            SUT.connected = True
                            time_stamp = random.randint(10, 10000)
                            qos = random.randint(0, 10)
                            retain = random.choice([True, False])
                            topic = helpers.random_string()
                            data = helpers.random_string()
                            SUT.publish_message(time_stamp, qos, retain, topic, data)

                            mock_reconnect.assert_not_called()
                            mock_publish.assert_called_once_with(topic, data, qos=qos, retain=retain)

    def test_publish_when_not_connected(self):
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
            'max_retries': random.randint(0, 10),
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.AbstractPublisher, '_reconnect') as mock_reconnect:
                        with mock.patch.object(user.mqttpublish.mqtt.Client, 'publish') as mock_publish:

                            SUT = self.class_under_test(mock_logger, mock_publisher, config)

                            SUT.connected = False
                            time_stamp = random.randint(10, 10000)
                            qos = random.randint(0, 10)
                            retain = random.choice([True, False])
                            topic = helpers.random_string()
                            data = helpers.random_string()
                            SUT.publish_message(time_stamp, qos, retain, topic, data)

                            mock_reconnect.assert_called_once_with()
                            mock_publish.assert_called_once_with(topic, data, qos=qos, retain=retain)

    def test_reconnect_connection(self):
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
            'max_retries': random.randint(0, 10),
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client,
                                           'reconnect',
                                           side_effect=mqttstubs.ClientStub.reconnect_with_connection,
                                           autospec=True) as mock_reconnect:

                        SUT = self.class_under_test(mock_logger, mock_publisher, config)
                        SUT._reconnect()

                        mock_reconnect.assert_called_once()

    def test_reconnect_no_connection(self):
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
            'max_retries': random.randint(0, 10),
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client,
                                           'reconnect',
                                           side_effect=mqttstubs.ClientStub.reconnect_without_connection,
                                           autospec=True) as mock_reconnect:

                        SUT = self.class_under_test(mock_logger, mock_publisher, config)
                        SUT._reconnect()

                        self.assertEqual(mock_reconnect.call_count, config_dict['max_retries'] + 1)


class TLSBase(unittest.TestCase):
    class_under_test = object
    protocol_string = None

    def test_tls_configuration_good(self):
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
            'max_retries': random.randint(0, 10),
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string()

            }
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set') as mock_tls_set:

                        self.class_under_test(mock_logger, mock_publisher, config)
                        mock_tls_set.assert_called_once_with(ca_certs=config_dict['tls']['ca_certs'],
                                                             certfile=None,
                                                             keyfile=None,
                                                             cert_reqs=ssl.CERT_REQUIRED,
                                                             tls_version=ssl.PROTOCOL_TLSv1_2,
                                                             ciphers=None)

    def test_missing_PROTOCOL_TLS(self):
        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        tls_version = 'tls'
        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': helpers.random_string(),
            'password': helpers.random_string(),
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'max_retries': random.randint(0, 10),
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'tls_version': tls_version,
            }
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_TLS
                            del ssl.PROTOCOL_TLS
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger, mock_publisher, config)
                        if saved_version:
                            ssl.PROTOCOL_TLS = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'tls_version'., {tls_version}")

    def test_missing_PROTOCOL_TLSv1(self):
        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        tls_version = 'tlsv1'
        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': helpers.random_string(),
            'password': helpers.random_string(),
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'max_retries': random.randint(0, 10),
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'tls_version': tls_version,
            }
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_TLSv1
                            del ssl.PROTOCOL_TLSv1
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger, mock_publisher, config)
                        if saved_version:
                            ssl.PROTOCOL_TLSv1 = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'tls_version'., {tls_version}")

    def test_missing_PROTOCOL_TLSv1_1(self):
        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        tls_version = 'tlsv1_1'
        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': helpers.random_string(),
            'password': helpers.random_string(),
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'max_retries': random.randint(0, 10),
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'tls_version': tls_version,
            }
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_TLSv1_1
                            del ssl.PROTOCOL_TLSv1_1
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger, mock_publisher, config)
                        if saved_version:
                            ssl.PROTOCOL_TLSv1_1 = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'tls_version'., {tls_version}")

    def test_missing_PROTOCOL_TLSv1_2(self):
        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        tls_version = 'tlsv1_2'
        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': helpers.random_string(),
            'password': helpers.random_string(),
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'max_retries': random.randint(0, 10),
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'tls_version': tls_version,
            }
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_TLSv1_2
                            del ssl.PROTOCOL_TLSv1_2
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger, mock_publisher, config)
                        if saved_version:
                            ssl.PROTOCOL_TLSv1_2 = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'tls_version'., {tls_version}")

    def test_missing_PROTOCOL_SSLv2(self):
        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        tls_version = 'sslv2'
        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': helpers.random_string(),
            'password': helpers.random_string(),
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'max_retries': random.randint(0, 10),
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'tls_version': tls_version,
            }
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_SSLv2
                            del ssl.PROTOCOL_SSLv2
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger, mock_publisher, config)
                        if saved_version:
                            ssl.PROTOCOL_SSLv2 = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'tls_version'., {tls_version}")

    def test_missing_PROTOCOL_SSLv23(self):
        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        tls_version = 'sslv23'
        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': helpers.random_string(),
            'password': helpers.random_string(),
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'max_retries': random.randint(0, 10),
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'tls_version': tls_version,
            }
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_SSLv23
                            del ssl.PROTOCOL_SSLv23
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger, mock_publisher, config)
                        if saved_version:
                            ssl.PROTOCOL_SSLv23 = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'tls_version'., {tls_version}")

    def test_missing_PROTOCOL_SSLv3(self):
        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        tls_version = 'sslv3'
        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': helpers.random_string(),
            'password': helpers.random_string(),
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'max_retries': random.randint(0, 10),
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'tls_version': tls_version,
            }
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_SSLv3
                            del ssl.PROTOCOL_SSLv3
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger, mock_publisher, config)
                        if saved_version:
                            ssl.PROTOCOL_SSLv3 = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'tls_version'., {tls_version}")

    def test_invalid_certs_required(self):
        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        certs_required = helpers.random_string()
        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': helpers.random_string(),
            'password': helpers.random_string(),
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'max_retries': random.randint(0, 10),
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'certs_required': certs_required
            }
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_SSLv3
                            del ssl.PROTOCOL_SSLv3
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger, mock_publisher, config)
                        if saved_version:
                            ssl.PROTOCOL_SSLv3 = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'certs_required'., {certs_required}")

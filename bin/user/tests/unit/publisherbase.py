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

import user.mqttcommon
import user.mqttpublish

class PublisherBase(unittest.TestCase):
    class_under_test = user.mqttpublish.Publisher
    protocol_string = None

    def test_get_client(self):
        raise NotImplementedError("test 'test_get_client' is not implemented")

    def test_set_callbacks(self):
        # pylint: disable=no-member

        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):

                    SUT = self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                    self.assertNotEqual(SUT.client.on_log, SUT.on_log)
                    self.assertNotEqual(SUT.client.on_connect, SUT.on_connect)
                    self.assertNotEqual(SUT.client.on_disconnect, SUT.on_disconnect)
                    self.assertNotEqual(SUT.client.on_publish, SUT.on_publish)

                    # The assigned callbacks must accept the calling convention of the api variant.
                    self._call_on_connect(SUT, 5)
                    self.assertIn('ERROR', [call[0][0]['log_type'] for call in mock_logger_queue.put.call_args_list])

    def test_set_on_log_callback(self):
        # pylint: disable=no-member

        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):

                    SUT = self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                    self.assertEqual(SUT.client.on_log, SUT.on_log)
                    self.assertNotEqual(SUT.client.on_connect, SUT.on_connect)
                    self.assertNotEqual(SUT.client.on_disconnect, SUT.on_disconnect)
                    self.assertNotEqual(SUT.client.on_publish, SUT.on_publish)

    def test_on_log(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
            with mock.patch.object(user.mqttpublish.Publisher, '_connect'):

                SUT = self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                level_dict = {
                    user.mqttpublish.mqtt.MQTT_LOG_INFO: 'INFO',
                    user.mqttpublish.mqtt.MQTT_LOG_NOTICE: 'INFO',
                    user.mqttpublish.mqtt.MQTT_LOG_WARNING: 'INFO',
                    user.mqttpublish.mqtt.MQTT_LOG_ERR: 'ERROR',
                    user.mqttpublish.mqtt.MQTT_LOG_DEBUG: 'DEBUG',
                }

                for level, log_type in level_dict.items():
                    msg = helpers.random_string()
                    mock_logger_queue.reset_mock()

                    SUT.on_log(None, None, level, msg)

                    mock_logger_queue.put.assert_called_once_with({'name': SUT.name,
                                                                   'log_type': log_type,
                                                                   'log_message': f"MQTT log: {msg}"})


                msg = helpers.random_string()
                mock_logger_queue.reset_mock()

                SUT.on_log(None, None, 0x20, msg)

                mock_logger_queue.put.assert_called_once_with({'name': SUT.name,
                                                               'log_type': None,
                                                               'log_message': f"MQTT log: {msg}"})

    def test_username_set(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'username_pw_set') as mock_username_pw_set:

                        self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                        mock_username_pw_set.assert_not_called()

    def test_password_set(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'username_pw_set') as mock_username_pw_set:

                        self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                        mock_username_pw_set.assert_not_called()

    def test_username_password_set(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'username_pw_set') as mock_username_pw_set:

                        self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                        mock_username_pw_set.assert_called_once_with(config_dict['username'], config_dict['password'])

    def test_connect_connection(self):
        mock_logger_queue = mock.Mock()
        mock_plugin_manager = mock.Mock()
        mock_publisher = mock.Mock()

        mock_plugin_manager.callbacks = {
            'on_mqtt_connect': {
                'immediate': {},
                'delay': {}
            },
        }

        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': None,
            'password': None,
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'min_delay': 1,
            'max_delay': 120,
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.mqtt.Client,
                                       'connect',
                                       side_effect=mqttstubs.ClientStub.connect_with_connection,
                                       autospec=True) as mock_connect:
                    with mock.patch.object(user.mqttpublish.mqtt.Client,
                                           'reconnect_delay_set',
                                           autospec=True) as mock_reconnect_delay:
                        with mock.patch.object(user.mqttpublish.mqtt.Client,
                                               'loop_start',
                                               autospec=True) as mock_loop_start:

                            self.class_under_test(mock_logger_queue, mock_plugin_manager, mock_publisher, config, monitor_dict, api=self.api)

                            self.assertEqual(mock_connect.call_count, 1)
                            mock_reconnect_delay.assert_called_once_with(mock.ANY,
                                                                         min_delay=config_dict['min_delay'],
                                                                         max_delay=config_dict['max_delay'])
                            # The network loop is started once; paho handles the CONNACK processing and reconnects.
                            mock_loop_start.assert_called_once_with(mock.ANY)

    def test_connect_no_connection(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.mqtt.Client,
                                       'connect',
                                       side_effect=mqttstubs.ClientStub.connect_without_connection,
                                       autospec=True) as mock_connect:
                    with mock.patch.object(user.mqttpublish.mqtt.Client,
                                           'loop_start',
                                           autospec=True) as mock_loop_start:

                        self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                        # A connect that does not raise is attempted once; the network loop waits for the CONNACK.
                        self.assertEqual(mock_connect.call_count, 1)
                        mock_loop_start.assert_called_once_with(mock.ANY)
                        log_messages = [call[0][0]['log_message'] for call in mock_logger_queue.put.call_args_list]
                        self.assertIn(f"Connecting to host: {config_dict['host']} port: {config_dict['port']}.", log_messages)

    def test_connect_first_call_exception(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.mqtt.Client,
                                       'connect',
                                       side_effect=mqttstubs.ClientStub.connect_exception_first_call,
                                       autospec=True) as mock_connect:
                    with mock.patch.object(user.mqttpublish.mqtt.Client,
                                           'loop_start',
                                           autospec=True) as mock_loop_start:

                        self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                        # A connect failure is not retried; it marks the publisher thread for shutdown, instead of raising.
                        self.assertEqual(mock_connect.call_count, 1)
                        mock_loop_start.assert_not_called()
                        self.assertFalse(mock_publisher.process)
                        log_messages = [call[0][0]['log_message'] for call in mock_logger_queue.put.call_args_list]
                        self.assertTrue(any("MQTT connect failed with" in msg for msg in log_messages))

    def test_connect_refused_connection(self):
        mock_logger_queue = mock.Mock()
        mock_plugin_manager = mock.Mock()
        mock_publisher = mock.Mock()

        mock_plugin_manager.callbacks = {
            'on_mqtt_connect': {
                'immediate': {},
                'delay': {}
            },
        }

        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': None,
            'password': None,
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'min_delay': 1,
            'max_delay': 120,
            'lwt': {
                'enable': True,
            }
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.mqtt.Client,
                                       'connect',
                                       side_effect=mqttstubs.ClientStub.connect_with_refused_connection,
                                       autospec=True) as mock_connect:
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'publish') as mock_publish:

                        SUT = self.class_under_test(mock_logger_queue, mock_plugin_manager, mock_publisher, config,
                                                    monitor_dict, api=self.api)

                        # A refused connection must not be treated as a connection. It is attempted once;
                        # paho's network loop retries with the configured backoff.
                        self.assertEqual(mock_connect.call_count, 1)
                        self.assertFalse(SUT.connected)
                        # The LWT 'online' payload must not be published for a refused connection.
                        mock_publish.assert_not_called()
                        self.assertIn('ERROR', [call[0][0]['log_type'] for call in mock_logger_queue.put.call_args_list])

    def test_on_connect_success(self):
        mock_logger_queue = mock.Mock()
        mock_plugin_manager = mock.Mock()
        mock_publisher = mock.Mock()

        mock_on_connect_callback = mock.Mock()
        mock_plugin_manager.callbacks = {
            'on_mqtt_connect': {
                'immediate': {
                    helpers.random_string(): mock_on_connect_callback,
                },
                'delay': {}
            },
        }

        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': None,
            'password': None,
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'min_delay': 1,
            'max_delay': 120,
            'lwt': {
                'enable': True,
            }
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        # Note: 'user.mqttpublish.time' is deliberately not mocked here. The monitor logging below
        # does arithmetic and numeric formatting on time.time(), which a MagicMock does not support.
        with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
            with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                with mock.patch.object(user.mqttpublish.mqtt.Client, 'publish') as mock_publish:

                    SUT = self.class_under_test(mock_logger_queue, mock_plugin_manager, mock_publisher, config,
                                                monitor_dict, api=self.api)

                    SUT.on_connect(SUT.client, None, {}, 0, None)

                    self.assertTrue(SUT.connected)
                    mock_on_connect_callback.assert_called_once()
                    mock_publish.assert_called_once()

    def test_on_connect_failure(self):
        mock_logger_queue = mock.Mock()
        mock_plugin_manager = mock.Mock()
        mock_publisher = mock.Mock()

        mock_on_connect_callback = mock.Mock()
        mock_plugin_manager.callbacks = {
            'on_mqtt_connect': {
                'immediate': {
                    helpers.random_string(): mock_on_connect_callback,
                },
                'delay': {}
            },
        }

        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': None,
            'password': None,
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'min_delay': 1,
            'max_delay': 120,
            'lwt': {
                'enable': True,
            }
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        # Note: 'user.mqttpublish.time' is deliberately not mocked here, so that time.time() returns
        # real numbers if on_connect() gets far enough to do monitor logging.
        with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
            with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                with mock.patch.object(user.mqttpublish.mqtt.Client, 'publish') as mock_publish:

                    SUT = self.class_under_test(mock_logger_queue, mock_plugin_manager, mock_publisher, config,
                                                monitor_dict, api=self.api)

                    SUT.on_connect(SUT.client, None, {}, 5, None)

                    self.assertFalse(SUT.connected)
                    mock_on_connect_callback.assert_not_called()
                    mock_publish.assert_not_called()
                    self.assertIn('ERROR', [call[0][0]['log_type'] for call in mock_logger_queue.put.call_args_list])

    def _call_on_connect(self, SUT, value):
        # The assigned callback is adapted to the calling convention of the api variant:
        # paho mqtt v1 calls on_connect with (client, userdata, flags, rc),
        # v2 with (client, userdata, flags, reason_code, properties).
        if self.api == user.mqttcommon.API_V1:
            SUT.client.on_connect(SUT.client, None, 0, value)
        else:
            SUT.client.on_connect(SUT.client, None, 0, mqttstubs.ReasonCodeStub(value), None)

    def _call_on_disconnect(self, SUT, value):
        SUT.on_disconnect(SUT.client, None, value, None)

    def test_on_disconnect(self):
        mock_logger_queue = mock.Mock()
        mock_plugin_manager = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
            with mock.patch.object(user.mqttpublish.Publisher, '_connect'):

                SUT = self.class_under_test(mock_logger_queue, mock_plugin_manager, mock_publisher, config,
                                            monitor_dict, api=self.api)

                # A disconnect requested by the client is a clean disconnect, so it is logged as INFO.
                SUT.connected = True
                self._call_on_disconnect(SUT, 0)
                self.assertFalse(SUT.connected)
                self.assertIn('INFO', [call[0][0]['log_type'] for call in mock_logger_queue.put.call_args_list])

                # An unexpected disconnect is logged as ERROR.
                mock_logger_queue.reset_mock()
                SUT.connected = True
                self._call_on_disconnect(SUT, 5)
                self.assertFalse(SUT.connected)
                self.assertIn('ERROR', [call[0][0]['log_type'] for call in mock_logger_queue.put.call_args_list])

    def test_on_message(self):
        mock_logger_queue = mock.Mock()
        mock_plugin_manager = mock.Mock()
        mock_publisher = mock.Mock()

        mock_immediate_callback = mock.Mock()
        mock_delay_callback = mock.Mock()
        mock_plugin_manager.callbacks = {
            'on_mqtt_message': {
                'immediate': {
                    helpers.random_string(): mock_immediate_callback,
                },
                'delay': {
                    helpers.random_string(): mock_delay_callback,
                }
            },
        }

        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': None,
            'password': None,
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'min_delay': 1,
            'max_delay': 120,
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        # Note: 'user.mqttpublish.time' is deliberately not mocked here. The monitor logging
        # does arithmetic and numeric formatting on time.time(), which a MagicMock does not support.
        with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
            with mock.patch.object(user.mqttpublish.Publisher, '_connect'):

                SUT = self.class_under_test(mock_logger_queue, mock_plugin_manager, mock_publisher, config,
                                            monitor_dict, api=self.api)

                userdata = helpers.random_string()
                msg = mqttstubs.Msg(helpers.random_string(), helpers.random_string(), 0, False)

                SUT.on_message(SUT.client, userdata, msg)

                mock_immediate_callback.assert_called_once_with(SUT.client, userdata, msg)
                mock_delay_callback.assert_called_once_with(SUT.client, userdata, msg)

    def test_on_message_with_no_callbacks(self):
        mock_logger_queue = mock.Mock()
        mock_plugin_manager = mock.Mock()
        mock_publisher = mock.Mock()

        mock_plugin_manager.callbacks = {
            'on_mqtt_message': {
                'immediate': {},
                'delay': {}
            },
        }

        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': None,
            'password': None,
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'min_delay': 1,
            'max_delay': 120,
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
            with mock.patch.object(user.mqttpublish.Publisher, '_connect'):

                SUT = self.class_under_test(mock_logger_queue, mock_plugin_manager, mock_publisher, config,
                                            monitor_dict, api=self.api)

                SUT.on_message(SUT.client, None, mqttstubs.Msg(helpers.random_string(),
                                                               helpers.random_string(),
                                                               0,
                                                               False))

                # The DEBUG 'Received' log plus the two empty loop summaries are always logged,
                # even when no plugins are registered for on_mqtt_message.
                log_messages = [call[0][0] for call in mock_logger_queue.put.call_args_list]
                self.assertTrue(any(entry['log_type'] == 'DEBUG' and 'Received:' in entry['log_message']
                                    for entry in log_messages))
                self.assertTrue(any('on_message (immediate)' in entry['log_message'] for entry in log_messages))
                self.assertTrue(any('on_message (delay)' in entry['log_message'] for entry in log_messages))

    def test_will_set_with_defaults(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
            'lwt': {
                'enable': True,
            }
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'will_set') as mock_will_set:

                        self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                        mock_will_set.assert_called_once_with(topic='status', payload='offline', qos=0, retain=True)

    def test_will_set_with_configured_values(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
            'lwt': {
                'enable': True,
                'topic': helpers.random_string(),
                'offline_payload': helpers.random_string(),
                'qos': random.randint(1, 5),
                'retain': False,
            }
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'will_set') as mock_will_set:

                        self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                        mock_will_set.assert_called_once_with(topic=config_dict['lwt']['topic'],
                                                              payload=config_dict['lwt']['offline_payload'],
                                                              qos=config_dict['lwt']['qos'],
                                                              retain=config_dict['lwt']['retain'])

    def test_publish_when_connected(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'publish') as mock_publish:
                        with mock.patch.object(user.mqttpublish.mqtt.Client, 'loop', autospec=True) as mock_loop:

                            SUT = self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                            SUT.connected = True
                            time_stamp = random.randint(10, 10000)
                            qos = random.randint(0, 10)
                            retain = random.choice([True, False])
                            topic = helpers.random_string()
                            data = helpers.random_string()
                            SUT.publish_message(time_stamp, qos, retain, topic, data)

                            mock_publish.assert_called_once_with(topic, data, qos=qos, retain=retain)
                            # paho's network loop thread owns the network loop; publishing must not pump it.
                            mock_loop.assert_not_called()

    def test_publish_when_not_connected(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'publish') as mock_publish:
                        with mock.patch.object(user.mqttpublish.mqtt.Client, 'loop', autospec=True) as mock_loop:

                            SUT = self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                            SUT.connected = False
                            time_stamp = random.randint(10, 10000)
                            qos = random.randint(0, 10)
                            retain = random.choice([True, False])
                            topic = helpers.random_string()
                            data = helpers.random_string()
                            SUT.publish_message(time_stamp, qos, retain, topic, data)

                            # Publishing while disconnected must not block on a reconnect. Paho queues the
                            # QOS>0 messages and delivers them when its network loop has reconnected.
                            mock_publish.assert_called_once_with(topic, data, qos=qos, retain=retain)
                            mock_loop.assert_not_called()

class TLSBase(unittest.TestCase):
    class_under_test = user.mqttpublish.Publisher
    protocol_string = None

    def test_tls_configuration_good(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string()

            }
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set') as mock_tls_set:

                        self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)
                        mock_tls_set.assert_called_once_with(ca_certs=config_dict['tls']['ca_certs'],
                                                             certfile=None,
                                                             keyfile=None,
                                                             cert_reqs=ssl.CERT_REQUIRED,
                                                             tls_version=ssl.PROTOCOL_TLSv1_2,
                                                             ciphers=None)

    def test_tls_configuration_normalizes_unset_options_to_none(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
            'tls': {
                'enable': True,
                'ca_certs': '',
                'certfile': 'none',
                'keyfile': 'None',
                'ciphers': 'NONE',
            }
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set') as mock_tls_set:

                        self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)
                        mock_tls_set.assert_called_once_with(ca_certs=None,
                                                             certfile=None,
                                                             keyfile=None,
                                                             cert_reqs=ssl.CERT_REQUIRED,
                                                             tls_version=ssl.PROTOCOL_TLSv1_2,
                                                             ciphers=None)

    def test_missing_PROTOCOL_TLS(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'tls_version': tls_version,
            }
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_TLS
                            del ssl.PROTOCOL_TLS
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)
                        if saved_version:
                            ssl.PROTOCOL_TLS = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'tls_version', {tls_version}")

    def test_missing_PROTOCOL_TLSv1(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'tls_version': tls_version,
            }
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_TLSv1
                            del ssl.PROTOCOL_TLSv1
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)
                        if saved_version:
                            ssl.PROTOCOL_TLSv1 = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'tls_version', {tls_version}")

    def test_missing_PROTOCOL_TLSv1_1(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'tls_version': tls_version,
            }
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_TLSv1_1
                            del ssl.PROTOCOL_TLSv1_1
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)
                        if saved_version:
                            ssl.PROTOCOL_TLSv1_1 = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'tls_version', {tls_version}")

    def test_missing_PROTOCOL_TLSv1_2(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'tls_version': tls_version,
            }
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_TLSv1_2
                            del ssl.PROTOCOL_TLSv1_2
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)
                        if saved_version:
                            ssl.PROTOCOL_TLSv1_2 = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'tls_version', {tls_version}")

    def test_missing_PROTOCOL_SSLv2(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'tls_version': tls_version,
            }
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_SSLv2
                            del ssl.PROTOCOL_SSLv2
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)
                        if saved_version:
                            ssl.PROTOCOL_SSLv2 = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'tls_version', {tls_version}")

    def test_missing_PROTOCOL_SSLv23(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'tls_version': tls_version,
            }
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_SSLv23
                            del ssl.PROTOCOL_SSLv23
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)
                        if saved_version:
                            ssl.PROTOCOL_SSLv23 = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'tls_version', {tls_version}")

    def test_missing_PROTOCOL_SSLv3(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'tls_version': tls_version,
            }
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_SSLv3
                            del ssl.PROTOCOL_SSLv3
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)
                        if saved_version:
                            ssl.PROTOCOL_SSLv3 = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'tls_version', {tls_version}")

    def test_invalid_certs_required(self):
        mock_logger_queue = mock.Mock()
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
            'min_delay': 1,
            'max_delay': 120,
            'tls': {
                'enable': True,
                'ca_certs': helpers.random_string(),
                'certs_required': certs_required
            }
        }
        config = configobj.ConfigObj(config_dict)

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                        try:
                            saved_version = ssl.PROTOCOL_SSLv3
                            del ssl.PROTOCOL_SSLv3
                        except AttributeError:
                            saved_version = None
                        with self.assertRaises(ValueError) as error:
                            self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)
                        if saved_version:
                            ssl.PROTOCOL_SSLv3 = saved_version
                        self.assertEqual(error.exception.args[0], f"Invalid 'certs_required', {certs_required}")

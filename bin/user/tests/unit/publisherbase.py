#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name
# pylint: disable=too-many-public-methods

import contextlib
import paho.mqtt
import random
import ssl

import unittest
import mock

import helpers
import mqttstubs

import user.mqttcommon
import user.mqttpublish
from user.tests.publish_helpers import create_monitor_config, create_publisher_config

# The TLS 1.2 default. A build without the legacy constant, as OpenSSL 4 is,
# reaches it through PROTOCOL_TLS_CLIENT, which means 'TLS 1.2 or newer'.
TLS_1_2 = getattr(ssl, 'PROTOCOL_TLSv1_2', ssl.PROTOCOL_TLS_CLIENT)


@contextlib.contextmanager
def patched_publisher(*, patch_time=True, patch_connect=True):
    """ Stack the common time, client-stub and connect patches. """
    with contextlib.ExitStack() as stack:
        if patch_time:
            stack.enter_context(mock.patch('user.mqttpublish.time'))
        stack.enter_context(mqttstubs.patch(user.mqttpublish.mqtt, 'Client', mqttstubs.ClientStub))
        if patch_connect:
            stack.enter_context(mock.patch.object(user.mqttpublish.Publisher, '_connect'))
        yield


class PublisherBase(unittest.TestCase):
    class_under_test = user.mqttpublish.Publisher
    # The paho api variant to test; the concrete subclasses set it.
    api = None
    protocol_string = None

    def test_get_client(self):
        raise NotImplementedError("test 'test_get_client' is not implemented")

    def test_set_callbacks(self):
        # pylint: disable=no-member

        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()

        config = create_publisher_config(self.protocol_string, log_mqtt=False)

        monitor_dict = create_monitor_config()

        with patched_publisher():

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

        config = create_publisher_config(self.protocol_string, log_mqtt=True)

        monitor_dict = create_monitor_config()

        with patched_publisher():

            SUT = self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

            self.assertEqual(SUT.client.on_log, SUT.on_log)
            self.assertNotEqual(SUT.client.on_connect, SUT.on_connect)
            self.assertNotEqual(SUT.client.on_disconnect, SUT.on_disconnect)
            self.assertNotEqual(SUT.client.on_publish, SUT.on_publish)

    def test_on_log(self):
        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()

        config = create_publisher_config(self.protocol_string, log_mqtt=True)

        monitor_dict = create_monitor_config()

        with patched_publisher(patch_time=False):

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

                mock_logger_queue.put.assert_called_once_with(
                    user.mqttcommon.Logger.create_entry(SUT.name, log_type, None, f"MQTT log: {msg}"))

            msg = helpers.random_string()
            mock_logger_queue.reset_mock()

            SUT.on_log(None, None, 0x20, msg)

            mock_logger_queue.put.assert_called_once_with(
                user.mqttcommon.Logger.create_entry(SUT.name, None, None, f"MQTT log: {msg}"))

    def test_username_set(self):
        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()

        config = create_publisher_config(self.protocol_string, username=helpers.random_string())

        monitor_dict = create_monitor_config()

        with patched_publisher():
            with mock.patch.object(user.mqttpublish.mqtt.Client, 'username_pw_set') as mock_username_pw_set:

                self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                mock_username_pw_set.assert_not_called()

    def test_password_set(self):
        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()

        config = create_publisher_config(self.protocol_string, password=helpers.random_string())

        monitor_dict = create_monitor_config()

        with patched_publisher():
            with mock.patch.object(user.mqttpublish.mqtt.Client, 'username_pw_set') as mock_username_pw_set:

                self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                mock_username_pw_set.assert_not_called()

    def test_username_password_set(self):
        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()

        config = create_publisher_config(self.protocol_string, username=helpers.random_string(), password=helpers.random_string())

        monitor_dict = create_monitor_config()

        with patched_publisher():
            with mock.patch.object(user.mqttpublish.mqtt.Client, 'username_pw_set') as mock_username_pw_set:

                self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                mock_username_pw_set.assert_called_once_with(config['username'], config['password'])

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

        config = create_publisher_config(self.protocol_string)

        monitor_dict = create_monitor_config()

        with patched_publisher(patch_connect=False):
            with mock.patch.object(user.mqttpublish.mqtt.Client,
                                   'connect_async',
                                   side_effect=mqttstubs.ClientStub.connect_with_connection,
                                   autospec=True) as mock_connect:
                with mock.patch.object(user.mqttpublish.mqtt.Client,
                                       'reconnect_delay_set',
                                       autospec=True) as mock_reconnect_delay:
                    with mock.patch.object(user.mqttpublish.mqtt.Client,
                                           'loop_start',
                                           autospec=True) as mock_loop_start:

                        self.class_under_test(mock_logger_queue, mock_plugin_manager, mock_publisher, config,
                                              monitor_dict, api=self.api)

                        self.assertEqual(mock_connect.call_count, 1)
                        mock_reconnect_delay.assert_called_once_with(mock.ANY,
                                                                     min_delay=config['min_delay'],
                                                                     max_delay=config['max_delay'])
                        # The network loop is started once; paho handles the CONNACK processing and reconnects.
                        mock_loop_start.assert_called_once_with(mock.ANY)

    def test_connect_no_connection(self):
        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()

        config = create_publisher_config(self.protocol_string)

        monitor_dict = create_monitor_config()

        with patched_publisher(patch_connect=False):
            with mock.patch.object(user.mqttpublish.mqtt.Client,
                                   'connect_async',
                                   side_effect=mqttstubs.ClientStub.connect_without_connection,
                                   autospec=True) as mock_connect:
                with mock.patch.object(user.mqttpublish.mqtt.Client,
                                       'loop_start',
                                       autospec=True) as mock_loop_start:

                    self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                    # The connection is started once; paho's network loop waits for the CONNACK and retries failures.
                    self.assertEqual(mock_connect.call_count, 1)
                    mock_loop_start.assert_called_once_with(mock.ANY)
                    self.assertTrue(mock_publisher.process)
                    log_messages = [call[0][0]['msg_text'] for call in mock_logger_queue.put.call_args_list]
                    self.assertIn(f"Connecting to {config['host']}:{config['port']}.", log_messages)

    def test_connect_option_exception(self):
        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()

        config = create_publisher_config(self.protocol_string)

        monitor_dict = create_monitor_config()

        with patched_publisher(patch_connect=False):
            with mock.patch.object(user.mqttpublish.mqtt.Client,
                                   'connect_async',
                                   side_effect=mqttstubs.ClientStub.connect_exception_first_call,
                                   autospec=True) as mock_connect:
                with mock.patch.object(user.mqttpublish.mqtt.Client,
                                       'loop_start',
                                       autospec=True) as mock_loop_start:

                    self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                    # An exception while starting the connection marks the publisher thread for shutdown.
                    self.assertEqual(mock_connect.call_count, 1)
                    mock_loop_start.assert_not_called()
                    self.assertFalse(mock_publisher.process)
                    log_messages = [call[0][0]['msg_text'] for call in mock_logger_queue.put.call_args_list]
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

        config = create_publisher_config(self.protocol_string, lwt={'enable': True})

        monitor_dict = create_monitor_config()

        with patched_publisher(patch_connect=False):
            with mock.patch.object(user.mqttpublish.mqtt.Client,
                                   'connect_async',
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

        config = create_publisher_config(self.protocol_string, lwt={'enable': True})

        monitor_dict = create_monitor_config()

        # time.time() must stay real; the monitor logging does arithmetic on it.
        with patched_publisher(patch_time=False):
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

        config = create_publisher_config(self.protocol_string, lwt={'enable': True})

        monitor_dict = create_monitor_config()

        # time.time() must stay real for on_connect's monitor logging.
        with patched_publisher(patch_time=False):
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

        mock_immediate_callback = mock.Mock()
        mock_delay_callback = mock.Mock()
        mock_plugin_manager.callbacks = {
            'on_mqtt_disconnect': {
                'immediate': {helpers.random_string(): mock_immediate_callback},
                'delay': {helpers.random_string(): mock_delay_callback},
            },
        }

        config = create_publisher_config(self.protocol_string)

        monitor_dict = create_monitor_config(monitor_on_disconnect='DEBUG')

        with patched_publisher(patch_time=False):

            SUT = self.class_under_test(mock_logger_queue, mock_plugin_manager, mock_publisher, config,
                                        monitor_dict, api=self.api)

            # A disconnect requested by the client is a clean disconnect, so it is logged as INFO.
            SUT.connected = True
            self._call_on_disconnect(SUT, 0)
            self.assertFalse(SUT.connected)
            self.assertIn('INFO', [call[0][0]['log_type'] for call in mock_logger_queue.put.call_args_list])
            mock_immediate_callback.assert_called_once_with(SUT.client, None, 0, None)
            mock_delay_callback.assert_called_once_with(SUT.client, None, 0, None)
            monitor_messages = [call[0][0]['msg_text'] for call in mock_logger_queue.put.call_args_list
                                if call[0][0]['log_type'] == 'DEBUG']
            self.assertTrue(any('on_disconnect (immediate)' in message for message in monitor_messages))
            self.assertTrue(any('on_disconnect (delay)' in message for message in monitor_messages))

            # An unexpected disconnect is logged as ERROR.
            mock_logger_queue.reset_mock()
            mock_immediate_callback.reset_mock()
            mock_delay_callback.reset_mock()
            SUT.connected = True
            self._call_on_disconnect(SUT, 5)
            self.assertFalse(SUT.connected)
            self.assertIn('ERROR', [call[0][0]['log_type'] for call in mock_logger_queue.put.call_args_list])
            mock_immediate_callback.assert_called_once_with(SUT.client, None, 5, None)
            mock_delay_callback.assert_called_once_with(SUT.client, None, 5, None)

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

        config = create_publisher_config(self.protocol_string)

        monitor_dict = create_monitor_config()

        # time.time() must stay real; the monitor logging does arithmetic on it.
        with patched_publisher(patch_time=False):

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

        config = create_publisher_config(self.protocol_string)

        monitor_dict = create_monitor_config()

        with patched_publisher(patch_time=False):

            SUT = self.class_under_test(mock_logger_queue, mock_plugin_manager, mock_publisher, config,
                                        monitor_dict, api=self.api)

            SUT.on_message(SUT.client, None, mqttstubs.Msg(helpers.random_string(),
                                                           helpers.random_string(),
                                                           0,
                                                           False))

            # The DEBUG 'Received' log plus the two empty loop summaries are always logged,
            # even when no plugins are registered for on_mqtt_message.
            log_messages = [call[0][0] for call in mock_logger_queue.put.call_args_list]
            self.assertTrue(any(entry['log_type'] == 'DEBUG' and 'Received:' in entry['msg_text']
                                for entry in log_messages))
            self.assertTrue(any('on_message (immediate)' in entry['msg_text'] for entry in log_messages))
            self.assertTrue(any('on_message (delay)' in entry['msg_text'] for entry in log_messages))

    def test_on_publish(self):
        mock_logger_queue = mock.Mock()
        mock_plugin_manager = mock.Mock()
        mock_publisher = mock.Mock()

        mock_immediate_callback = mock.Mock()
        mock_delay_callback = mock.Mock()
        mock_plugin_manager.callbacks = {
            'on_mqtt_publish': {
                'immediate': {
                    helpers.random_string(): mock_immediate_callback,
                },
                'delay': {
                    helpers.random_string(): mock_delay_callback,
                }
            },
        }

        config = create_publisher_config(self.protocol_string)

        monitor_dict = create_monitor_config()

        # time.time() must stay real; the monitor logging does arithmetic on it.
        with patched_publisher(patch_time=False):

            SUT = self.class_under_test(mock_logger_queue, mock_plugin_manager, mock_publisher, config,
                                        monitor_dict, api=self.api)

            userdata = helpers.random_string()
            mid = random.randint(1, 65535)
            properties = helpers.random_string()

            SUT.on_publish(SUT.client, userdata, mid, properties)

            mock_immediate_callback.assert_called_once_with(SUT.client, userdata, mid, properties)
            mock_delay_callback.assert_called_once_with(SUT.client, userdata, mid, properties)

    def test_on_publish_with_no_callbacks(self):
        mock_logger_queue = mock.Mock()
        mock_plugin_manager = mock.Mock()
        mock_publisher = mock.Mock()

        mock_plugin_manager.callbacks = {
            'on_mqtt_publish': {
                'immediate': {},
                'delay': {}
            },
        }

        config = create_publisher_config(self.protocol_string)

        monitor_dict = create_monitor_config()

        with patched_publisher(patch_time=False):

            SUT = self.class_under_test(mock_logger_queue, mock_plugin_manager, mock_publisher, config,
                                        monitor_dict, api=self.api)

            SUT.on_publish(SUT.client, None, random.randint(1, 65535), None)

            # The DEBUG 'published' log plus the two empty loop summaries are always logged,
            # even when no plugins are registered for on_mqtt_publish.
            log_messages = [call[0][0] for call in mock_logger_queue.put.call_args_list]
            self.assertTrue(any(entry['log_type'] == 'DEBUG' and 'published:' in entry['msg_text']
                                for entry in log_messages))
            self.assertTrue(any('on_publish (immediate)' in entry['msg_text'] for entry in log_messages))
            self.assertTrue(any('on_publish (delay)' in entry['msg_text'] for entry in log_messages))

    def test_will_set_with_defaults(self):
        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()

        config = create_publisher_config(self.protocol_string,
                                         username=helpers.random_string(),
                                         password=helpers.random_string(),
                                         lwt={'enable': True})

        monitor_dict = create_monitor_config()

        with patched_publisher():
            with mock.patch.object(user.mqttpublish.mqtt.Client, 'will_set') as mock_will_set:

                self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                mock_will_set.assert_called_once_with(topic='status', payload='offline', qos=0, retain=True)

    def test_will_set_with_configured_values(self):
        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()

        config = create_publisher_config(self.protocol_string,
                                         username=helpers.random_string(),
                                         password=helpers.random_string(),
                                         lwt={'enable': True,
                                              'topic': helpers.random_string(),
                                              'offline_payload': helpers.random_string(),
                                              'qos': random.randint(1, 5),
                                              'retain': False})

        monitor_dict = create_monitor_config()

        with patched_publisher():
            with mock.patch.object(user.mqttpublish.mqtt.Client, 'will_set') as mock_will_set:

                self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                mock_will_set.assert_called_once_with(topic=config['lwt']['topic'],
                                                      payload=config['lwt']['offline_payload'],
                                                      qos=config['lwt']['qos'],
                                                      retain=config['lwt']['retain'])

    def test_publish_when_connected(self):
        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()

        config = create_publisher_config(self.protocol_string, username=helpers.random_string(), password=helpers.random_string())

        monitor_dict = create_monitor_config()

        with patched_publisher():
            with mock.patch.object(user.mqttpublish.mqtt.Client, 'publish') as mock_publish:
                with mock.patch.object(user.mqttpublish.mqtt.Client, 'loop', autospec=True) as mock_loop:
                    mock_publish.return_value.rc = paho.mqtt.client.MQTT_ERR_SUCCESS

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

        config = create_publisher_config(self.protocol_string, username=helpers.random_string(), password=helpers.random_string())

        monitor_dict = create_monitor_config()

        with patched_publisher():
            with mock.patch.object(user.mqttpublish.mqtt.Client, 'publish') as mock_publish:
                with mock.patch.object(user.mqttpublish.mqtt.Client, 'loop', autospec=True) as mock_loop:
                    mock_publish.return_value.rc = paho.mqtt.client.MQTT_ERR_SUCCESS

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

    def _publish_while_not_connected(self, qos, rc):
        """ Publish one message as paho refusing it with rc, returning the topic, log entries and publisher. """
        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()

        config = create_publisher_config(self.protocol_string, username=helpers.random_string(), password=helpers.random_string())

        monitor_dict = create_monitor_config()

        with mock.patch('user.mqttpublish.time'):
            with mqttstubs.patch(user.mqttpublish.mqtt, "Client", mqttstubs.ClientStub):
                with mock.patch.object(user.mqttpublish.Publisher, '_connect'):
                    with mock.patch.object(user.mqttpublish.mqtt.Client, 'publish') as mock_publish:
                        mock_publish.return_value.rc = rc

                        SUT = self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)

                        SUT.connected = False
                        time_stamp = random.randint(10, 10000)
                        retain = random.choice([True, False])
                        topic = helpers.random_string()
                        data = helpers.random_string()
                        SUT.publish_message(time_stamp, qos, retain, topic, data)

                        return topic, [call[0][0] for call in mock_logger_queue.put.call_args_list], SUT

    def test_publish_when_not_connected_at_qos_0(self):
        # At QoS 0 paho drops the message while disconnected, which is what at-most-once permits.
        topic, log_messages, SUT = self._publish_while_not_connected(0, paho.mqtt.client.MQTT_ERR_NO_CONN)

        self.assertFalse(any(entry['log_type'] == 'ERROR' and topic in entry['msg_text']
                             for entry in log_messages))
        self.assertEqual(SUT.inflight, {})

    def test_publish_when_not_connected_above_qos_0(self):
        # Paho queues a QoS > 0 message and sends it after reconnecting, so nothing was lost.
        topic, log_messages, SUT = self._publish_while_not_connected(random.randint(1, 10), paho.mqtt.client.MQTT_ERR_NO_CONN)

        self.assertFalse(any(entry['log_type'] == 'ERROR' and topic in entry['msg_text']
                             for entry in log_messages))
        self.assertEqual(len(SUT.inflight), 1)

    def test_publish_when_not_accepted(self):
        # A publish paho refuses for any reason other than the connection is logged, not raised.
        topic, log_messages, SUT = self._publish_while_not_connected(random.randint(0, 10), paho.mqtt.client.MQTT_ERR_QUEUE_SIZE)

        self.assertTrue(any(entry['log_type'] == 'ERROR' and topic in entry['msg_text']
                            for entry in log_messages))
        self.assertEqual(SUT.inflight, {})

    def test_publish_message_callbacks(self):
        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()
        mock_plugin_manager = mock.Mock()

        mock_immediate_callback = mock.Mock()
        mock_delay_callback = mock.Mock()
        mock_plugin_manager.callbacks = {
            'mqtt_publish': {
                'immediate': {
                    helpers.random_string(): mock_immediate_callback,
                },
                'delay': {
                    helpers.random_string(): mock_delay_callback,
                }
            },
        }

        config = create_publisher_config(self.protocol_string, username=helpers.random_string(), password=helpers.random_string())

        monitor_dict = create_monitor_config()

        with patched_publisher():
            with mock.patch.object(user.mqttpublish.mqtt.Client, 'publish') as mock_publish:
                mid = random.randint(1, 65535)
                mock_publish.return_value.mid = mid
                mock_publish.return_value.rc = paho.mqtt.client.MQTT_ERR_SUCCESS

                SUT = self.class_under_test(mock_logger_queue, mock_plugin_manager, mock_publisher, config,
                                            monitor_dict, api=self.api)

                time_stamp = random.randint(10, 10000)
                qos = random.randint(0, 2)
                retain = random.choice([True, False])
                topic = helpers.random_string()
                data = helpers.random_string()

                SUT.publish_message(time_stamp, qos, retain, topic, data)

                # The immediate callbacks run before the publish, so the mid and rc are not known.
                mock_immediate_callback.assert_called_once_with(
                    SUT.client, None, None, topic, data, qos, retain, time_stamp)
                # The delay callbacks run after the publish and can capture the mid.
                mock_delay_callback.assert_called_once_with(
                    SUT.client, mid, int(paho.mqtt.client.MQTT_ERR_SUCCESS), topic, data, qos, retain, time_stamp)

    def test_publish_message_tracks_inflight(self):
        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()

        config = create_publisher_config(self.protocol_string, username=helpers.random_string(), password=helpers.random_string())

        monitor_dict = create_monitor_config()

        with patched_publisher():
            with mock.patch.object(user.mqttpublish.mqtt.Client, 'publish') as mock_publish:
                mid = random.randint(1, 65535)
                mock_publish.return_value.mid = mid
                mock_publish.return_value.rc = paho.mqtt.client.MQTT_ERR_SUCCESS

                SUT = self.class_under_test(mock_logger_queue, None, mock_publisher, config,
                                            monitor_dict, api=self.api)

                SUT.publish_message(random.randint(10, 10000), 0, False,
                                    helpers.random_string(), helpers.random_string())

                self.assertIs(SUT.inflight[mid], mock_publish.return_value)

    def test_wait_for_inflight_messages(self):
        mock_logger_queue = mock.Mock()

        config = create_publisher_config(self.protocol_string, username=helpers.random_string(), password=helpers.random_string())

        monitor_dict = create_monitor_config()

        with patched_publisher(patch_time=False):
            SUT = self.class_under_test(mock_logger_queue, None, mock.Mock(), config,
                                        monitor_dict, api=self.api)

            mqtt_message_info = mock.Mock()
            mqtt_message_info.rc = paho.mqtt.client.MQTT_ERR_SUCCESS
            mqtt_message_info.is_published.return_value = False
            SUT.inflight = {42: mqtt_message_info}

            SUT.wait_for_inflight_messages(5)

            mqtt_message_info.wait_for_publish.assert_called_once()
            self.assertEqual(SUT.inflight, {})

    def test_wait_for_inflight_messages_disabled(self):
        mock_logger_queue = mock.Mock()

        config = create_publisher_config(self.protocol_string, username=helpers.random_string(), password=helpers.random_string())

        monitor_dict = create_monitor_config()

        with patched_publisher(patch_time=False):
            SUT = self.class_under_test(mock_logger_queue, None, mock.Mock(), config,
                                        monitor_dict, api=self.api)

            mqtt_message_info = mock.Mock()
            SUT.inflight = {42: mqtt_message_info}

            SUT.wait_for_inflight_messages(0)

            mqtt_message_info.wait_for_publish.assert_not_called()

class TLSBase(unittest.TestCase):
    class_under_test = user.mqttpublish.Publisher
    # The paho api variant to test; the concrete subclasses set it.
    api = None
    protocol_string = None

    def _assert_missing_tls_option(self, option, value, ssl_attr):
        """ Hiding an ssl constant must make the publisher reject the option. """
        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()
        config = create_publisher_config(
            self.protocol_string,
            username=helpers.random_string(),
            password=helpers.random_string(),
            tls={'enable': True, 'ca_certs': helpers.random_string(), option: value})
        monitor_dict = create_monitor_config()

        with patched_publisher():
            with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set'):
                try:
                    saved_version = getattr(ssl, ssl_attr)
                    delattr(ssl, ssl_attr)
                except AttributeError:
                    saved_version = None
                with self.assertRaises(ValueError) as error:
                    self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)
                if saved_version:
                    setattr(ssl, ssl_attr, saved_version)
                self.assertEqual(error.exception.args[0], f"Invalid '{option}', {value}.")

    def test_tls_configuration_good(self):
        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()

        config = create_publisher_config(self.protocol_string,
                                         username=helpers.random_string(),
                                         password=helpers.random_string(),
                                         tls={'enable': True, 'ca_certs': helpers.random_string()})

        monitor_dict = create_monitor_config()

        with patched_publisher():
            with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set') as mock_tls_set:

                self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)
                mock_tls_set.assert_called_once_with(ca_certs=config['tls']['ca_certs'],
                                                     certfile=None,
                                                     keyfile=None,
                                                     cert_reqs=ssl.CERT_REQUIRED,
                                                     tls_version=TLS_1_2,
                                                     ciphers=None)

    def test_tls_configuration_normalizes_unset_options_to_none(self):
        mock_logger_queue = mock.Mock()
        mock_publisher = mock.Mock()

        config = create_publisher_config(self.protocol_string,
                                         username=helpers.random_string(),
                                         password=helpers.random_string(),
                                         tls={'enable': True, 'ca_certs': '', 'certfile': 'none', 'keyfile': 'None', 'ciphers': 'NONE'})

        monitor_dict = create_monitor_config()

        with patched_publisher():
            with mock.patch.object(user.mqttpublish.mqtt.Client, 'tls_set') as mock_tls_set:

                self.class_under_test(mock_logger_queue, None, mock_publisher, config, monitor_dict, api=self.api)
                mock_tls_set.assert_called_once_with(ca_certs=None,
                                                     certfile=None,
                                                     keyfile=None,
                                                     cert_reqs=ssl.CERT_REQUIRED,
                                                     tls_version=TLS_1_2,
                                                     ciphers=None)

    def test_missing_PROTOCOL_TLS(self):
        self._assert_missing_tls_option('tls_version', 'tls', 'PROTOCOL_TLS')

    def test_missing_PROTOCOL_TLSv1(self):
        self._assert_missing_tls_option('tls_version', 'tlsv1', 'PROTOCOL_TLSv1')

    def test_missing_PROTOCOL_TLSv1_1(self):
        self._assert_missing_tls_option('tls_version', 'tlsv1_1', 'PROTOCOL_TLSv1_1')

    def test_missing_PROTOCOL_TLSv1_2(self):
        self._assert_missing_tls_option('tls_version', 'tlsv1_2', 'PROTOCOL_TLSv1_2')

    def test_missing_PROTOCOL_SSLv2(self):
        self._assert_missing_tls_option('tls_version', 'sslv2', 'PROTOCOL_SSLv2')

    def test_missing_PROTOCOL_SSLv23(self):
        self._assert_missing_tls_option('tls_version', 'sslv23', 'PROTOCOL_SSLv23')

    def test_missing_PROTOCOL_SSLv3(self):
        self._assert_missing_tls_option('tls_version', 'sslv3', 'PROTOCOL_SSLv3')

    def test_invalid_certs_required(self):
        self._assert_missing_tls_option('certs_required', helpers.random_string(), 'PROTOCOL_SSLv3')

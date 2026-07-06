#    Copyright (c) 2025-2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

"""
Publish to MQTT on loop or archive creation.
"""

import queue as Queue

import abc
import json
import logging
import random
import ssl
import threading
import time

import configobj
import paho.mqtt.client as mqtt

import weeutil
from weeutil.weeutil import to_bool, to_float, to_int, to_list

import weewx
import weewx.defaults
from weewx.engine import StdService

VERSION = "1.1.0-rc07b"

class CannotConnectError(ConnectionError):
    """" Cannot connect to broker. """

# log = logging.getLogger(__name__)
def setup_logging(logging_level, config_dict):
    """ Setup logging for running in standalone mode."""
    if logging_level:
        weewx.debug = logging_level

    weeutil.logger.setup('wee_MQTTSS', config_dict)

class Logger:
    ''' Manage the logging '''
    def __init__(self):
        self.log = logging.getLogger(__name__)

    def logdbg(self, msg):
        """ log debug messages """
        self.log.debug("%s %s", threading.get_native_id(), msg)

    def loginf(self, msg):
        """ log informational messages """
        self.log.info("%s %s", threading.get_native_id(), msg)

    def logerr(self, msg):
        """ log error messages """
        self.log.error("%s %s", threading.get_native_id(), msg)

class PluginManager():
    """ Manage the plugin callbacks. """
    def __init__(self, logger):
        self.logger = logger
        self.plugins = {}
        self.callbacks = {
            'on_weewx_data': {
                'immediate': {},
                'delay': {}
            },
            'on_mqtt_connect': {
                'immediate': {},
                'delay': {}
            },
            'on_mqtt_message': {
                'immediate': {},
                'delay': {}
            },
            'update_record': {
                'immediate': {},
                'delay': {}
            },
        }

    def create_plugin(self, plugin_name, plugin_dict, topics, weewx_dict):
        """ Create the plugin. """
        self.plugins[plugin_name] = {}
        plugin_class = weeutil.weeutil.get_object(plugin_name)
        plugin = plugin_class(self.logger, plugin_name, plugin_dict, topics, weewx_dict)
        self.plugins[plugin_name]['plugin'] = plugin
        callbacks = plugin.get_callbacks()
        for callback in callbacks:
            for callback_name in callback:
                timing = callback[callback_name]['timing']
                self.callbacks[callback_name][timing][plugin_name] = callback[callback_name]['callback']

class AbstractPublisher(abc.ABC):
    """ Managing publishing to MQTT. """
    def __init__(self, logger, plugin_manager, publisher, mqtt_config):
        self.logger = logger
        self.plugin_manager = plugin_manager
        self.connected = False
        self.mqtt_logger = {
            mqtt.MQTT_LOG_INFO: self.logger.loginf,
            mqtt.MQTT_LOG_NOTICE: self.logger.loginf,
            mqtt.MQTT_LOG_WARNING: self.logger.loginf,
            mqtt.MQTT_LOG_ERR: self.logger.logerr,
            mqtt.MQTT_LOG_DEBUG: self.logger.logdbg
        }

        self.publisher = publisher
        self.mqtt_config = mqtt_config

        # Number of seconds to wait for connection processing
        # ToDo: make configurable
        self.wait_for_connection = 1

        self.client = self.get_client(mqtt_config['clientid'], mqtt_config['protocol'])
        self.set_callbacks(mqtt_config['log_mqtt'])

        if mqtt_config['username'] is not None and mqtt_config['password'] is not None:
            self.client.username_pw_set(mqtt_config['username'], mqtt_config['password'])

        tls_dict = mqtt_config.get('tls')
        if tls_dict and to_bool(tls_dict.get('enable', True)):
            self._config_tls(tls_dict)

        self.lwt_dict = mqtt_config.get('lwt')
        if self.lwt_dict is not None and to_bool(self.lwt_dict.get('enable', True)):
            self.client.will_set(topic=self.lwt_dict.get('topic', 'status'),
                                 payload=self.lwt_dict.get('offline_payload', 'offline'),
                                 qos=to_int(self.lwt_dict.get('qos', 0)),
                                 retain=to_bool(self.lwt_dict.get('retain', True)))

        self._connect()

    @classmethod
    def get_publisher(cls, logger, plugin_manager, publisher, mqtt_config):
        ''' Factory method to get appropriate MQTTPublish for paho mqtt version. '''
        if hasattr(mqtt, 'CallbackAPIVersion'):
            protocol = mqtt_config['protocol']
            if protocol in [mqtt.MQTTv31, mqtt.MQTTv311]:
                return PublisherV2MQTT3(logger, plugin_manager, publisher, mqtt_config)

            return PublisherV2(logger, plugin_manager, publisher, mqtt_config)

        return PublisherV1(logger, plugin_manager, publisher, mqtt_config)

    def _connect(self):
        try:
            self.connect(self.mqtt_config['host'], self.mqtt_config['port'], self.mqtt_config['keepalive'])
        except Exception as exception:  # want to catch all pylint: disable=broad-exception-caught
            self.logger.logerr(f"MQTT connect failed with {type(exception)} and reason {exception}.")
        retries = 0
        # Give the connection logic some time to execute
        time.sleep(self.wait_for_connection)
        # Allow the MQTT processing to happen, after allowing the connection processing to complete.
        self.client.loop(timeout=0.1)
        while not self.connected and self.publisher.running:
            self.logger.loginf(f"Waiting {self.mqtt_config['wait_between_retries']} seconds to connect.")
            # loop seems to break before connect, perhaps due to logging
            self.client.loop(timeout=0.1)
            time.sleep(self.mqtt_config['wait_between_retries'])

            retries += 1
            if retries > self.mqtt_config['max_retries']:
                # Shut thread down, a bit of a hack
                self.publisher.running = False
                return

            try:
                self.connect(self.mqtt_config['host'], self.mqtt_config['port'], self.mqtt_config['keepalive'])
                time.sleep(self.wait_for_connection)
                self.client.loop(timeout=.1)
                self.logger.logdbg("After retrying connect call.")
            except Exception as exception:  # want to catch all pylint: disable=broad-exception-caught
                self.logger.logerr(f"MQTT connect retry {retries} failed with {type(exception)} and reason {exception}.")

    def _reconnect(self):
        self.logger.logdbg("Attempting to reconnect.")
        try:
            self.client.reconnect()
        except Exception as exception:  # want to catch all pylint: disable=broad-exception-caught
            self.logger.logerr(f"MQTT reconnect failed with {type(exception)} and reason {exception}.")
        self.logger.logdbg("After reconnect call.")
        retries = 0
        time.sleep(self.wait_for_connection)
        self.client.loop(timeout=0.1)
        while not self.connected and self.publisher.running:
            self.logger.loginf(f"Waiting {self.mqtt_config['wait_between_retries']} seconds to (re)connect.")
            self.client.loop(timeout=0.1)
            time.sleep(self.mqtt_config['wait_between_retries'])

            retries += 1
            if retries > self.mqtt_config['max_retries']:
                raise CannotConnectError

            try:
                self.client.reconnect()
                time.sleep(self.wait_for_connection)
                self.client.loop(timeout=.1)
                self.logger.logdbg("After retrying reconnect call.")
            except Exception as exception:  # want to catch all pylint: disable=broad-exception-caught
                self.logger.logerr(f"MQTT reconnect {retries} failed with {type(exception)} and reason {exception}.")

    def _config_tls(self, tls_dict):
        """ Configure TLS."""
        valid_cert_reqs = {
            'none': ssl.CERT_NONE,
            'optional': ssl.CERT_OPTIONAL,
            'required': ssl.CERT_REQUIRED
        }

        # Some versions are dependent on the OpenSSL install
        valid_tls_versions = {}
        try:
            valid_tls_versions['tls'] = ssl.PROTOCOL_TLS
        except AttributeError:
            pass
        try:
            valid_tls_versions['tlsv1'] = ssl.PROTOCOL_TLSv1
        except AttributeError:
            pass
        try:
            valid_tls_versions['tlsv11'] = ssl.PROTOCOL_TLSv1_1
        except AttributeError:
            pass
        try:
            valid_tls_versions['tlsv12'] = ssl.PROTOCOL_TLSv1_2
        except AttributeError:
            pass
        try:
            valid_tls_versions['sslv2'] = ssl.PROTOCOL_SSLv2
        except AttributeError:
            pass
        try:
            valid_tls_versions['sslv23'] = ssl.PROTOCOL_SSLv23
        except AttributeError:
            pass
        try:
            valid_tls_versions['sslv3'] = ssl.PROTOCOL_SSLv3
        except AttributeError:
            pass

        ca_certs = tls_dict.get('ca_certs')
        if ca_certs == '':
            ca_certs = None

        certfile = tls_dict.get('certfile')
        if certfile and certfile.lower() == 'none':
            certfile = None

        keyfile = tls_dict.get('keyfile')
        if keyfile and keyfile.lower() == 'none':
            keyfile = None

        ciphers = tls_dict.get('ciphers')
        if ciphers and ciphers.lower() == 'none':
            ciphers = None

        valid_cert_reqs = valid_cert_reqs.get(tls_dict.get('certs_required', 'required'))
        if valid_cert_reqs is None:
            raise ValueError(f"Invalid 'certs_required'., {tls_dict['certs_required']}")

        tls_version = valid_tls_versions.get(tls_dict.get('tls_version', 'tlsv12'))
        if tls_version is None:
            raise ValueError(f"Invalid 'tls_version'., {tls_dict['tls_version']}")

        self.client.tls_set(ca_certs=ca_certs,
                            certfile=certfile,
                            keyfile=keyfile,
                            cert_reqs=valid_cert_reqs,
                            tls_version=tls_version,
                            ciphers=ciphers)

    def publish_message(self, time_stamp, qos, retain, topic, data):
        """ Publish the message. """
        if not self.connected:
            self._reconnect()
        # self.logger.logdbg(f"publishing: {topic} {data}")

        mqtt_message_info = self.client.publish(topic, data, qos=qos, retain=retain)
        self.logger.logdbg(f"At {int(time.time())} publishing: {int(time_stamp)} {mqtt_message_info.mid} {qos} {topic}")

        self.client.loop(timeout=0.1)

    def get_client(self, client_id, protocol):
        ''' Get the MQTT client. '''
        raise NotImplementedError("Method 'get_client' is not implemented")

    def set_callbacks(self, log_mqtt):
        ''' Setup the MQTT callbacks. '''
        raise NotImplementedError("Method 'set_callbacks' is not implemented")

    def connect(self, host, port, keepalive):
        ''' Connect to the MQTT server. '''
        raise NotImplementedError("Method 'connect' is not implemented")

    def on_log(self, client, userdata, level, msg):
        """ The on_log callback. """
        raise NotImplementedError("Method 'on_log' is not implemented")

    def on_connect(self, client, userdata, flags, reason_code, properties):
        """ The on_connect callback.
            The signature differs between V1 and V2 of paho.mqtt, with more added in V2.
            So, in V1 the additional paramters are made as 'optional'."""
        raise NotImplementedError("Method 'on_connect' is not implemented")

    def on_disconnect(self, client, userdata, flags_rc, reason_code, properties):
        """ The on_disconnect callback.
            The signature differs between V1 and V2 of paho.mqtt, with more added in V2.
            So, in V1 the additional paramters are made as 'optional'."""
        raise NotImplementedError("Method 'on_disconnect' is not implemented")

    def on_publish(self, client, userdata, mid, reason_codes, properties):
        """ The on_publish callback.
            The signature differs between V1 and V2 of paho.mqtt, with more added in V2.
            So, in V1 the additional paramters are made as 'optional'."""
        raise NotImplementedError("Method 'on_publish' is not implemented")

    def on_message(self, client, userdata, msg):
        """ The on_message callback. """
        self.logger.logdbg(f"Received: {userdata} {msg}")
        for plugin_name in self.plugin_manager.callbacks['on_mqtt_message']['immediate']:
            self.plugin_manager.callbacks['on_mqtt_message']['immediate'][plugin_name](client, userdata, msg)

        for plugin_name in self.plugin_manager.callbacks['on_mqtt_message']['delay']:
            self.plugin_manager.callbacks['on_mqtt_message']['delay'][plugin_name](client, userdata, msg)

class PublisherV1(AbstractPublisher):
    ''' MQTTPublish that communicates with paho mqtt v1.'''
    def __init__(self, logger, plugin_manager, publisher, mqtt_config):
        protocol = mqtt_config['protocol']
        if protocol not in [mqtt.MQTTv31, mqtt.MQTTv311]:
            raise ValueError(f"Invalid protocol, {protocol}.")

        super().__init__(logger, plugin_manager, publisher, mqtt_config)

    def get_client(self, client_id, protocol):
        return mqtt.Client(  # depends on version of paho.mqtt pylint: disable=no-value-for-parameter
            client_id=client_id,
            protocol=protocol)

    def set_callbacks(self, log_mqtt):
        if log_mqtt:
            self.client.on_log = self.on_log

        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_publish = self.on_publish
        self.client.on_message = self.on_message

    def connect(self, host, port, keepalive):
        self.client.connect(host, port, keepalive)

    def on_log(self, _client, _userdata, level, msg):
        self.mqtt_logger[level](f"MQTT log: {msg}")

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        # https://pypi.org/project/paho-mqtt/#on-connect
        # reason_code:
        # 0: Connection successful
        # 1: Connection refused - incorrect protocol version
        # 2: Connection refused - invalid client identifier
        # 3: Connection refused - server unavailable
        # 4: Connection refused - bad username or password
        # 5: Connection refused - not authorised
        # 6-255: Currently unused.
        self.logger.loginf(f"Connected with result code {int(reason_code)}, {mqtt.error_string(reason_code)}")
        self.logger.loginf(f"Connected flags {str(flags)}")

        for plugin_name in self.plugin_manager.callbacks['on_mqtt_connect']['immediate']:
            self.plugin_manager.callbacks['on_mqtt_connect']['immediate'][plugin_name](client,
                                                                                       userdata,
                                                                                       flags,
                                                                                       reason_code,
                                                                                       properties)

        if self.lwt_dict is not None and to_bool(self.lwt_dict.get('enable', True)):
            self.client.publish(topic=self.lwt_dict.get('topic', 'status'),
                                payload=self.lwt_dict.get('online_payload', 'online'),
                                qos=to_int(self.lwt_dict.get('qos', 0)),
                                retain=to_bool(self.lwt_dict.get('retain', True)))

        for plugin_name in self.plugin_manager.callbacks['on_mqtt_connect']['delay']:
            self.plugin_manager.callbacks['on_mqtt_connect']['delay'][plugin_name](client, userdata, flags, reason_code, properties)

        self.connected = True

    def on_disconnect(self, _client, _userdata, flags_rc, reason_code=None, properties=None):
        # https://pypi.org/project/paho-mqtt/#on-discconnect
        # The rc parameter indicates the disconnection state.
        # If MQTT_ERR_SUCCESS (0), the callback was called in response to a disconnect() call.
        # If any other value the disconnection was unexpected,
        # such as might be caused by a network error.
        rc = flags_rc
        if rc == 0:
            self.logger.loginf(f"Disconnected with result code {int(rc)}, {mqtt.error_string(rc)}")
        else:
            self.logger.logerr(f"Disconnected with result code {int(rc)}, {mqtt.error_string(rc)}")

        # As of 1.6.1, Paho MQTT cannot have a callback invoke a second callback. So we won't attempt to reconnect here.
        # Because that would cause the on_connect callback to be called. Instead we will just mark as not connected.
        # And check the flag before attempting to publish.
        self.connected = False

    def on_publish(self, _client, _userdata, mid, reason_codes=None, properties=None):
        time_stamp = "          "
        qos = ""
        self.logger.logdbg(f"At {int(time.time())} published: {time_stamp} {mid} {qos}")

class PublisherV2(AbstractPublisher):
    ''' MQTTPublish that communicates with paho mqtt v2. '''
    def get_client(self, client_id, protocol):
        return mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                           protocol=protocol,
                           client_id=client_id)

    def set_callbacks(self, log_mqtt):
        if log_mqtt:
            self.client.on_log = self.on_log

        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_publish = self.on_publish
        self.client.on_message = self.on_message

    def connect(self, host, port, keepalive):
        self.client.connect(host=host, port=port, keepalive=keepalive, clean_start=True)

    def on_log(self, _client, _userdata, level, msg):
        self.mqtt_logger[level](f"MQTT log: {msg}")

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self.logger.loginf(f"Connected with result code {int(int(reason_code.value))}")
        self.logger.loginf(f"Connected flags {str(flags)}")

        for plugin_name in self.plugin_manager.callbacks['on_mqtt_connect']['immediate']:
            self.plugin_manager.callbacks['on_mqtt_connect']['immediate'][plugin_name](client,
                                                                                       userdata,
                                                                                       flags,
                                                                                       reason_code,
                                                                                       properties)

        if self.lwt_dict is not None and to_bool(self.lwt_dict.get('enable', True)):
            self.client.publish(topic=self.lwt_dict.get('topic', 'status'),
                                payload=self.lwt_dict.get('online_payload', 'online'),
                                qos=to_int(self.lwt_dict.get('qos', 0)),
                                retain=to_bool(self.lwt_dict.get('retain', True)))

        for plugin_name in self.plugin_manager.callbacks['on_mqtt_connect']['delay']:
            self.plugin_manager.callbacks['on_mqtt_connect']['delay'][plugin_name](client, userdata, flags, reason_code, properties)

        self.connected = True

    def on_disconnect(self, _client, _userdata, _flags, reason_code, _properties):
        # https://pypi.org/project/paho-mqtt/#on-discconnect
        # The rc parameter indicates the disconnection state.
        # If MQTT_ERR_SUCCESS (0), the callback was called in response to a disconnect() call.
        # If any other value the disconnection was unexpected,
        # such as might be caused by a network error.
        if int(reason_code.value) == 0:
            self.logger.loginf(f"Disconnected with result code {int(int(reason_code.value))}")
        else:
            self.logger.logerr(f"Disconnected with result code {int(int(reason_code.value))}")

        # ToDo: research how it works with v2
        # As of 1.6.1, Paho MQTT cannot have a callback invoke a second callback. So we won't attempt to reconnect here.
        # Because that would cause the on_connect callback to be called. Instead we will just mark as not connected.
        # And check the flag before attempting to publish.
        self.connected = False

    def on_publish(self, _client, _userdata, mid, _reason_codes, _properties):
        time_stamp = "          "
        qos = ""
        self.logger.logdbg(f"At {int(time.time())} published: {time_stamp} {mid} {qos}")

class PublisherV2MQTT3(PublisherV2):
    ''' MQTTPublish that communicates with paho mqtt v2. '''
    def get_client(self, client_id, protocol):
        return mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                           protocol=protocol,
                           client_id=client_id,
                           userdata=None,
                           clean_session=True)

    def connect(self, host, port, keepalive):
        self.client.connect(host=host, port=port, keepalive=keepalive)

class PublishWeeWX():
    """ Backwards compatibility class."""
    def __init__(self, engine, config_dict):
        self.mqtt_publish = MQTTPublish(engine, config_dict)

    def shutDown(self):  # Needed for backward compatibility pylint: disable=invalid-name
        """Run when an engine shutdown is requested."""
        self.mqtt_publish.shutDown()

class MQTTPublish(StdService):
    """ A service to publish WeeWX loop and/or archive data to MQTT. """
    def __init__(self, engine, config_dict):
        super().__init__(engine, config_dict)
        self.logger = Logger()

        self.logger.loginf(f"MQTTPublish version: {VERSION}.")

        service_dict = config_dict.get('MQTTPublish', {})
        self.plugins = service_dict.get('plugins', {})

        exclude_keys = ['password']
        sanitized_service_dict = {k: service_dict[k] for k in set(list(service_dict.keys())) - set(exclude_keys)}
        self.logger.logdbg(f"sanitized configuration removed {exclude_keys}")
        self.logger.logdbg(f"sanitized_service_dict is {sanitized_service_dict}")

        #  backwards compatability
        if 'PublishWeeWX' in service_dict.sections:
            self.logger.logerr("'PublishWeeWX' is deprecated. Move options to top level, '[MQTTPublish]'.")
            service_dict = config_dict.get('MQTTPublish', {}).get('PublishWeeWX', {})

        self.enable = to_bool(service_dict.get('enable', True))
        if not self.enable:
            self.logger.loginf("Not enabled, exiting.")
            return

        data_binding = service_dict.get('data_binding', 'wx_binding')
        self.manager_dict = weewx.manager.get_manager_dict_from_config(config_dict, data_binding)

        self.weewx_dict = {}
        self.weewx_dict['stn_info'] = engine.stn_info
        self.weewx_dict['manager_dict'] = self.manager_dict
        self.weewx_dict['defaults'] = weeutil.config.deep_copy(weewx.defaults.defaults)
        self.weewx_dict['defaults'].interpolation = False
        if 'Defaults' in config_dict['StdReport']:
            weeutil.config.merge_config(self.weewx_dict['defaults'], config_dict['StdReport']['Defaults'])

        self.topics_loop, self.topics_archive, binding = self.configure_topics(service_dict)
        # self.logger.logdbg(f"archive topic configuration is: {self.topics_archive}")
        # self.logger.logdbg(f"loop topic configuration is: {self.topics_loop}")

        self.mqtt_config = {}
        self.mqtt_config['keepalive'] = to_int(service_dict.get('keepalive', 60))

        self.mqtt_config['max_retries'] = to_int(service_dict.get('max_retries', 5))
        self.mqtt_config['wait_between_retries'] = to_int(service_dict.get('wait_between_retries', 5))
        self.mqtt_config['log_mqtt'] = to_bool(service_dict.get('mqtt_log', False))
        self.mqtt_config['host'] = service_dict.get('host', 'localhost')
        self.mqtt_config['port'] = to_int(service_dict.get('port', 1883))
        self.mqtt_config['username'] = service_dict.get('username', None)
        self.mqtt_config['password'] = service_dict.get('password', None)
        self.mqtt_config['clientid'] = service_dict.get('clientid', 'MQTTPublish-' + str(random.randint(1000, 9999)))

        protocol_string = service_dict.get('protocol', 'MQTTv311')
        self.mqtt_config['protocol'] = getattr(mqtt, protocol_string, 0)

        self.mqtt_config['tls'] = service_dict.get('tls')
        self.mqtt_config['lwt'] = service_dict.get('lwt')

        sanitized_mqtt_config = {k: self.mqtt_config[k] for k in set(list(self.mqtt_config.keys())) - set(exclude_keys)}
        self.logger.logdbg(f"sanitized mqtt_config removed {exclude_keys}")
        self.logger.logdbg(f"sanitized_mqtt_config is {sanitized_mqtt_config}")

        self.max_thread_restarts = to_int(service_dict.get('max_thread_restarts', 2))
        # ToDo: change this so it gets reset to zero when the thread is fully up and running (connected) - not as easy as it sounds
        self.thread_restarts = 0

        if 'binding' in service_dict:
            self.logger.loginf("'binding' is deprecated and no longer used.")

        self.data_queue = Queue.Queue()

        if 'loop' in binding:
            self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)

        if 'archive' in binding:
            self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

        self._thread = PublishWeeWXThread(self.logger,
                                          self.plugins,
                                          self.weewx_dict,
                                          self.manager_dict,
                                          self.mqtt_config,
                                          self.topics_loop,
                                          self.topics_archive,
                                          self.data_queue)
        self.thread_start()

    def configure_fields(self,
                         fields_dict,
                         ignore,
                         publish_none_value,
                         append_unit_label,
                         conversion_type,
                         format_string):
        """ Configure the fields. """
        fields = {}
        if fields_dict:
            for field in fields_dict.sections:
                fields[field] = {}
                field_dict = fields_dict.get(field, {})
                fields[field]['name'] = field_dict.get('name', field)
                fields[field]['unit'] = field_dict.get('unit', None)
                fields[field]['ignore'] = to_bool(field_dict.get('ignore', ignore))
                fields[field]['publish_none_value'] = to_bool(field_dict.get('publish_none_value', publish_none_value))
                fields[field]['append_unit_label'] = to_bool(field_dict.get('append_unit_label', append_unit_label))
                fields[field]['conversion_type'] = field_dict.get('conversion_type', conversion_type)
                fields[field]['format_string'] = field_dict.get('format_string', format_string)

        # self.logger.logdbg(f"Configured fields: {fields}.")
        return fields

    def configure_topics(self, service_dict):
        """ Configure the topics. """

        if 'topics' not in service_dict:
            raise ValueError("[[topics]] is required.")

        default_qos = to_int(service_dict.get('qos', 0))
        default_retain = to_bool(service_dict.get('retain', False))
        default_type = service_dict.get('type', 'json')
        default_binding = ['archive', 'loop']

        default_append_label = service_dict.get('append_unit_label', True)
        default_conversion_type = service_dict.get('conversion_type', 'string')
        default_format_string = service_dict.get('format_string', None)

        topics_loop = {}
        topics_archive = {}
        event_binding = {}
        for topic in service_dict['topics'].sections:
            topic_dict = service_dict['topics'].get(topic, {})
            publish = to_bool(topic_dict.get('publish', True))
            qos = to_int(topic_dict.get('qos', default_qos))
            retain = to_bool(topic_dict.get('retain', default_retain))
            data_type = topic_dict.get('type', default_type)
            binding = weeutil.weeutil.option_as_list(topic_dict.get('binding', default_binding))
            unit_system_name = topic_dict.get('unit_system', service_dict.get('unit_system', 'US'))
            unit_system = weewx.units.unit_constants[unit_system_name]

            ignore = to_bool(topic_dict.get('ignore', False))
            publish_none_value = to_bool(topic_dict.get('publish_none_value', False))
            append_unit_label = to_bool(topic_dict.get('append_unit_label', default_append_label))
            conversion_type = topic_dict.get('conversion_type', default_conversion_type)
            format_string = topic_dict.get('format_string', default_format_string)
            fields_dict = topic_dict.get('fields', None)
            fields = {}
            if fields_dict is not None:
                fields = self.configure_fields(fields_dict,
                                               ignore,
                                               publish_none_value,
                                               append_unit_label,
                                               conversion_type,
                                               format_string)

            aggregates = topic_dict.get('aggregates', {})
            if aggregates:
                # Temporarily build the MQTTAggregateValues plugin configuration
                self.logger.logerr(("'[aggregates]' is deprecated and has moved to a plugin. "
                                    "To configure see, https://weewx-mqtt.github.io/publish/plugins/aggregatevalues/"))
                if 'MQTTAggregateValues' not in self.plugins:
                    self.plugins['MQTTAggregateValues'] = {}
                    self.plugins['MQTTAggregateValues']['module'] = 'user.mqttaggregatevalues'
                if 'topics' not in self.plugins['MQTTAggregateValues']:
                    self.plugins['MQTTAggregateValues']['topics'] = {}
                for aggregate in topic_dict['aggregates']:
                    self.plugins['MQTTAggregateValues']['topics'][topic] = {}
                    self.plugins['MQTTAggregateValues']['topics'][topic][aggregate] = topic_dict['aggregates'][aggregate]

            for ignore_field in to_list(topic_dict.get('ignore_fields', [])):
                fields[ignore_field] = {
                    'ignore': True
                }

            if 'loop' in binding:
                if not publish:
                    continue
                topics_loop[topic] = {}
                topics_loop[topic]['qos'] = qos
                topics_loop[topic]['retain'] = retain
                topics_loop[topic]['type'] = data_type
                topics_loop[topic]['unit_system'] = unit_system
                topics_loop[topic]['guarantee_delivery'] = to_bool(topic_dict.get('guarantee_delivery', False))
                if topics_loop[topic]['guarantee_delivery'] and topics_loop[topic]['qos'] == 0:
                    raise ValueError("QOS must be greater than 0 to guarantee delivery.")
                topics_loop[topic]['ignore'] = ignore
                topics_loop[topic]['append_unit_label'] = append_unit_label
                topics_loop[topic]['conversion_type'] = conversion_type
                topics_loop[topic]['format_string'] = format_string
                topics_loop[topic]['fields'] = dict(fields)
                event_binding['loop'] = True

            if 'archive' in binding:
                if not publish:
                    continue
                topics_archive[topic] = {}
                topics_archive[topic]['qos'] = qos
                topics_archive[topic]['retain'] = retain
                topics_archive[topic]['type'] = data_type
                topics_archive[topic]['unit_system'] = unit_system
                topics_archive[topic]['guarantee_delivery'] = to_bool(topic_dict.get('guarantee_delivery', False))
                if topics_archive[topic]['guarantee_delivery'] and topics_archive[topic]['qos'] == 0:
                    raise ValueError("QOS must be greater than 0 to guarantee delivery.")
                topics_archive[topic]['ignore'] = ignore
                topics_archive[topic]['append_unit_label'] = append_unit_label
                topics_archive[topic]['conversion_type'] = conversion_type
                topics_archive[topic]['format_string'] = format_string
                topics_archive[topic]['fields'] = dict(fields)
                event_binding['archive'] = True

        self.logger.logdbg(f"Loop topics: {topics_loop}")
        self.logger.logdbg(f"Archive topics: {topics_archive}")
        return topics_loop, topics_archive, event_binding.keys()

    def thread_start(self):
        """Start the publishing thread."""
        self.logger.loginf("Starting thread.")
        self._thread.start()
        # ToDo: configure how long to wait for thread to start
        self.thread_start_wait = 5.0
        self.logger.loginf("Joining thread.")
        # self._thread.join(self.thread_start_wait)
        self.logger.loginf("Joined thread.")

        if not self._thread.is_alive():
            raise weewx.WakeupError("Unable to start MQTT publishing thread.")

        self.logger.loginf("Thread started.")

    def new_loop_packet(self, event):
        """ Handle loop packets. """
        self._handle_record('loop', event.packet)

    def new_archive_record(self, event):
        """ Handle archive records. """
        self._handle_record('archive', event.record)

    def _handle_record(self, data_type, data):
        if not self._thread.is_alive():
            if self.thread_restarts < self.max_thread_restarts:
                self.thread_restarts += 1
                self._thread = \
                    PublishWeeWXThread(self.logger,
                                       self.plugins,
                                       self.weewx_dict,
                                       self.manager_dict,
                                       self.mqtt_config,
                                       self.topics_loop,
                                       self.topics_archive,
                                       self.data_queue)
                self.thread_start()

                self.data_queue.put({'time_stamp': data['dateTime'], 'type': data_type, 'data': data})
                self._thread.threading_event.set()
            else:
                raise weewx.StopNow("MQTT publishing thread has stopped.")
        else:
            self.data_queue.put({'time_stamp': data['dateTime'], 'type': data_type, 'data': data})
            self._thread.threading_event.set()

    def shutDown(self):
        """Run when an engine shutdown is requested."""
        self.logger.loginf("Shutdown initiatead")
        if self._thread:
            self.logger.loginf("Shutdown of thread initiated")
            self._thread.process = False
            self._thread.threading_event.set()
            self._thread.join(20.0)
            if self._thread.is_alive():
                self.logger.logerr(f"Unable to shut down {self._thread.name} thread")

            self._thread = None

class PublishWeeWXThread(threading.Thread):
    """Publish WeeWX data to MQTT. """
    UNIT_REDUCTIONS = {
        'degree_F': 'F',
        'degree_C': 'C',
        'inch': 'in',
        'mile_per_hour': 'mph',
        'mile_per_hour2': 'mph',
        'km_per_hour': 'kph',
        'km_per_hour2': 'kph',
        'knot': 'knot',
        'knot2': 'knot2',
        'meter_per_second': 'mps',
        'meter_per_second2': 'mps',
        'degree_compass': None,
        'watt_per_meter_squared': 'Wpm2',
        'uv_index': None,
        'percent': None,
        'unix_epoch': None,
    }

    def __init__(self,
                 logger,
                 plugins,
                 weewx_dict,
                 manager_dict,
                 mqtt_config,
                 topics_loop,
                 topics_archive,
                 data_queue):
        threading.Thread.__init__(self)
        self.logger = logger

        self.logger.loginf("Initializing publishing thread.")

        self.plugins = plugins
        self.weewx_dict = weewx_dict
        self.manager_dict = manager_dict
        self.publisher = None

        self.db_manager = None
        self.plugin_manager = None

        self.mqtt_config = mqtt_config
        self.topics_loop = topics_loop
        self.topics_archive = topics_archive
        self.all_topics = {**self.topics_loop, **self.topics_archive}
        self.lwt_dict = mqtt_config.get('lwt')

        self.data_queue = data_queue
        self.threading_event = threading.Event()

        # Flag to control thread running.
        # Setting to False will stop the thread.
        self.process = True

    def update_record(self, topic_dict, record):
        """ Update the record. """
        final_record = {}
        updated_record = weewx.units.to_std_system(record, topic_dict['unit_system'])
        # self.logger.logdbg(f"record after unit conversion is: {updated_record}")

        for field in updated_record:
            fieldinfo = topic_dict['fields'].get(field, {})
            ignore = fieldinfo.get('ignore', topic_dict.get('ignore'))
            publish_none_value = fieldinfo.get('publish_none_value', topic_dict.get('publish_none_value'))

            if ignore:
                continue
            if updated_record[field] is None and not publish_none_value:
                continue

            (name, value) = self.update_field(topic_dict,
                                              fieldinfo,
                                              field,
                                              updated_record[field],
                                              updated_record['usUnits'])
            final_record[name] = value
        # self.logger.logdbg(f"record after field updates is: {final_record}")

        # self.logger.logdbg(f"record after aggregation calculation is:  {final_record}")
        return final_record

    @staticmethod
    def update_field(topic_dict, fieldinfo, field, value, unit_system):
        """ Update field. """
        name = fieldinfo.get('name', field)
        unit = fieldinfo.get('unit', None)
        append_unit_label = fieldinfo.get('append_unit_label', topic_dict.get('append_unit_label'))

        if append_unit_label:
            if unit is None:
                (unit_type, _) = weewx.units.getStandardUnitType(unit_system, name)
            else:
                unit_type = unit
            unit_type = PublishWeeWXThread.UNIT_REDUCTIONS.get(unit_type, unit_type)
            if unit_type is not None:
                name = f"{name}_{unit_type}"

        unit = fieldinfo.get('unit', None)
        if unit is not None:
            (from_unit, from_group) = weewx.units.getStandardUnitType(unit_system, field)
            from_tuple = (value, from_unit, from_group)
            converted_value = weewx.units.convert(from_tuple, unit)[0]
        else:
            converted_value = value

        conversion_type = fieldinfo.get('conversion_type', topic_dict.get('conversion_type'))
        format_string = fieldinfo.get('format_string', topic_dict.get('format_string'))
        if conversion_type == 'integer':
            converted_value = to_int(converted_value)
        elif conversion_type == 'float':
            converted_value = to_float(converted_value)

        if format_string is not None:
            formatted_value = format_string % converted_value
        else:
            formatted_value = converted_value

        return name, formatted_value

    def publish_row(self, time_stamp, data, topics):
        """ Publish the data. """
        record = data

        for topic in topics:
            for plugin_name in self.publisher.plugin_manager.callbacks['update_record']['immediate']:
                self.publisher.plugin_manager.callbacks['update_record']['immediate'][plugin_name](self.publisher.client,
                                                                                                   topic,
                                                                                                   record,
                                                                                                   data['usUnits'],
                                                                                                   topics[topic]['qos'],
                                                                                                   topics[topic]['retain'])
            updated_record = self.update_record(topics[topic], record)
            for plugin_name in self.publisher.plugin_manager.callbacks['update_record']['delay']:
                # Note, this is called wit the unit_system from the configuration because:
                # 1. The record has been converted to this unit_system
                # 2. The record may not be publishing the field usUnits.
                self.publisher.plugin_manager.callbacks['update_record']['delay'][plugin_name](self.publisher.client,
                                                                                               topic,
                                                                                               updated_record,
                                                                                               topics[topic]['unit_system'],
                                                                                               topics[topic]['qos'],
                                                                                               topics[topic]['retain'])

            if topics[topic]['type'] == 'json':
                self.publisher.publish_message(time_stamp,
                                               topics[topic]['qos'],
                                               topics[topic]['retain'],
                                               topic,
                                               json.dumps(updated_record))
            if topics[topic]['type'] == 'keyword':
                data_keyword = ', '.join(f"{key}={val}" for (key, val) in updated_record.items())
                self.publisher.publish_message(time_stamp,
                                               topics[topic]['qos'],
                                               topics[topic]['retain'],
                                               topic,
                                               data_keyword)
            if topics[topic]['type'] == 'individual':
                for key, value in updated_record.items():
                    self.publisher.publish_message(time_stamp,
                                                   topics[topic]['qos'],
                                                   topics[topic]['retain'],
                                                   topic + '/' + key,
                                                   value)

    def run(self):
        self.logger.loginf(f"Starting publishing loop {self.name}.")
        threading.current_thread().name = f"MQTTPublish-{threading.get_native_id()}"

        self.plugin_manager = PluginManager(self.logger)
        for plugin in self.plugins:
            plugin_name = self.plugins[plugin]['module'] + '.' + plugin
            self.plugin_manager.create_plugin(plugin_name, self.plugins[plugin], self.all_topics, self.weewx_dict)

        # need to instantiate inside thread
        self.publisher = AbstractPublisher.get_publisher(self.logger, self.plugin_manager, self, self.mqtt_config)

        with weewx.manager.open_manager(self.manager_dict) as db_manager:
            self.db_manager = db_manager
            while self.process:
                try:
                    data2 = self.data_queue.get_nowait()
                    # self.logger.logdbg(f"pulled from the data_queue: {data2}")
                    for plugin_name in self.plugin_manager.callbacks['on_weewx_data']['immediate']:
                        self.plugin_manager.callbacks['on_weewx_data']['immediate'][plugin_name](data2)

                    time_stamp = data2['time_stamp']
                    data_type = data2['type']
                    data = data2['data']
                    if data_type == 'loop':
                        self.publish_row(time_stamp, data, self.topics_loop)
                    elif data_type == 'archive':
                        self.publish_row(time_stamp, data, self.topics_archive)
                    else:
                        self.logger.logerr(f"Unknown data type, {data_type}")

                    for plugin_name in self.plugin_manager.callbacks['on_weewx_data']['delay']:
                        self.plugin_manager.callbacks['on_weewx_data']['delay'][plugin_name](data2)
                except Queue.Empty:
                    # ToDo: this causes another connection, seems to cause no harm
                    # does cause a socket error/disconnect message on the server
                    self.publisher.client.loop(timeout=0.1)
                    # ToDo: - investigate my 'sleep' implementation
                    self.threading_event.wait(self.mqtt_config['keepalive'] / 4)
                    self.threading_event.clear()
                except CannotConnectError:
                    self.process = False

        # MQTT's LWT is sent from the broker on an unexpected disconnect.
        # So we need to send an offline message on an 'expected' disconnect.
        if self.lwt_dict is not None and to_bool(self.lwt_dict.get('enable', True)):
            self.publisher.client.publish(topic=self.lwt_dict.get('topic', 'status'),
                                          payload=self.lwt_dict.get('offline_payload', 'offline'),
                                          qos=to_int(self.lwt_dict.get('qos', 0)),
                                          retain=to_bool(self.lwt_dict.get('retain', True)))

        self.publisher.client.disconnect()
        self.logger.loginf(f"Exited publishing loop {self.name}.")

if __name__ == "__main__":
    import argparse
    import os

    def main():  # pragma: no cover
        """ Run it. """
        parser = argparse.ArgumentParser()
        parser.add_argument('--version', action='version', version=f'%(prog)s {VERSION}')

        parser.add_argument("--messages", required=True, type=str, dest="message_file",
                            help="The file with the test messages")

        parser.add_argument("config_file")

        options = parser.parse_args()

        message_file = options.message_file

        config_path = os.path.abspath(options.config_file)
        config = configobj.ConfigObj(config_path, file_error=True)

        min_config_dict = {
            'Station': {
                'altitude': [0, 'foot'],
                'latitude': 0,
                'station_type': 'Simulator',
                'longitude': 0
            },
            'Simulator': {
                'driver': 'weewx.drivers.simulator',
            },
            'Engine': {
                'Services': {}
            }
        }
        engine = weewx.engine.StdEngine(min_config_dict)

        setup_logging(True, config)
        mqtt_publish = MQTTPublish(engine, config)

        with open(message_file, encoding='UTF-8') as file_object:
            packets = json.load(file_object)

        for packet in packets:
            for key in packet.keys():
                obs = packet[key]
                if isinstance(obs, str) and obs.lower() == 'none':
                    packet[key] = None
            new_loop_packet_event = weewx.Event(weewx.NEW_LOOP_PACKET, packet=packet)
            engine.dispatchEvent(new_loop_packet_event)

        # Attempt to wait for all packets to be processed
        # ToDo: Add a max number of time the sleep/loop runs
        while mqtt_publish._thread.threading_event.is_set():  # pylint: disable=protected-access
            print("sleepting")
            time.sleep(1)

        mqtt_publish.shutDown()

    main()

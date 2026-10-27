#    Copyright (c) 2025-2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

"""
Publish to MQTT on loop or archive creation.
"""

import queue as Queue

import copy
import json
import multiprocessing
import os
import random
import sys
import threading
import time
import configobj
import paho.mqtt.client as mqtt

# When running 'standalone' in a package install or git 'install', need to know where the WeeWX modules are
bin_root = os.getenv('BIN_ROOT')
if bin_root is not None:
    sys.path.append(bin_root)

# And the mqttpublish module
user_root = os.getenv('USER_ROOT')
if user_root is not None:
    sys.path.append(user_root + '/..')

# pylint: disable=wrong-import-position
import weeutil
from weeutil.weeutil import to_bool, to_float, to_int, to_list, startOfInterval

import weewx
import weewx.defaults
from weewx.engine import StdService
from user import mqttcommon
# pylint: enable=wrong-import-position

# All the weewx-mqtt extensions ship their own copy of mqttcommon. Fail loudly when the
# loaded copy is older than this extension needs, instead of with a mysterious error later.
if getattr(mqttcommon, 'MQTTCOMMON_API', (0, 0)) < (1, 0):
    raise ImportError("user.mqttcommon is too old. An older weewx-mqtt extension likely overwrote it during"
                      " install; reinstall or upgrade all the weewx-mqtt extensions.")

VERSION = "1.3.0-rc02a"

def setup_logging(logging_level, config_dict):
    """ Setup logging for running in standalone mode."""
    if logging_level:
        weewx.debug = logging_level

    weeutil.logger.setup('wee_MQTTPublish', config_dict)

class MQTTPlugin():  # pylint: disable=too-few-public-methods
    """ Common plugin initialization. """
    def __init__(self, logger_queue, name, plugin_dict):
        self.logger_queue = logger_queue
        self.plugin_dict = weeutil.config.deep_copy(plugin_dict)
        self.enabled = to_bool(self.plugin_dict.get('enable', True))
        self.name = f"{self.__class__.__name__}-{threading.get_native_id()}"

        if not self.enabled:
            self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'INFO', None, f"Plugin {name} is not enabled."))

class PluginManager():  # pylint: disable=too-few-public-methods
    """ Manage the plugin callbacks. """
    def __init__(self, logger, monitor_config, mqtt_dict, topics, weewx_dict):  # pylint: disable=too-many-arguments
        self.logger = logger
        self.monitor_config = monitor_config
        self.mqtt_dict = mqtt_dict
        self.topics = topics
        self.weewx_dict = weewx_dict
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

    def create_plugin(self, name, plugin_name, plugin_dict):
        """ Create the plugin. """
        self.plugins[name] = {}
        plugin_class = weeutil.weeutil.get_object(plugin_name)
        plugin = plugin_class(self.logger, self.monitor_config, plugin_name,
                              plugin_dict, self.mqtt_dict, self.topics, self.weewx_dict)
        self.plugins[name]['plugin'] = plugin
        callbacks = plugin.get_callbacks()
        for callback in callbacks:
            for callback_name in callback:
                timing = callback[callback_name]['timing']
                self.callbacks[callback_name][timing][name] = callback[callback_name]['callback']

class Publisher:  # pylint: disable=too-many-instance-attributes
    """ Managing publishing to MQTT. """

    def __init__(self, logger_queue, plugin_manager, publisher, mqtt_config, monitor_config, *, api=None):  # pylint: disable=R0913
        # The paho mqtt api variant to communicate with. It defaults to the selection for the protocol.
        self.api = self._resolve_api(mqtt_config['protocol'], api)

        self.logger_queue = logger_queue
        self.plugin_manager = plugin_manager
        self.connected = False
        self.mqtt_logger = mqttcommon.PAHO_LOG_LEVELS
        self.name = f"{self.__class__.__name__}-{threading.get_native_id()}"

        self.publisher = publisher
        self.mqtt_config = mqtt_config

        self.monitor_on_message = monitor_config['monitor_on_message']
        self.monitor_on_connect = monitor_config['monitor_on_connect']

        self.client = self.get_client(mqtt_config['clientid'], mqtt_config['protocol'])
        self.set_callbacks(mqtt_config['log_mqtt'])

        mqttcommon.apply_credentials(self.client, mqtt_config['username'], mqtt_config['password'])

        tls_dict = mqtt_config.get('tls')
        if tls_dict and to_bool(tls_dict.get('enable', True)):
            self._config_tls(tls_dict)

        self.lwt_dict = mqtt_config.get('lwt')
        if self.lwt_dict is not None and to_bool(self.lwt_dict.get('enable', True)):
            topic = self.lwt_dict.get('topic', 'status')
            payload = self.lwt_dict.get('offline_payload', 'offline')
            qos = to_int(self.lwt_dict.get('qos', 0))
            retain = to_bool(self.lwt_dict.get('retain', True))
            self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'INFO', None,
                                                                 f"Enabling LWT: topic: {topic}, payload: {payload}, "
                                                                 f"qos: {qos}, retain: {retain}"))
            self.client.will_set(topic=topic, payload=payload, qos=qos, retain=retain)

        self._connect()

    @staticmethod
    def _resolve_api(protocol, api):
        ''' Resolve the paho mqtt api variant to communicate with, defaulting to the selection for the protocol. '''
        if api is None:
            api = mqttcommon.select_api(protocol)
        if api == mqttcommon.API_V1 and protocol not in mqttcommon.MQTT3_PROTOCOLS:
            raise ValueError(f"Invalid protocol, {protocol}.")

        return api

    def _connect(self):
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'INFO', None,
                                                             f"Connecting to host: {self.mqtt_config['host']} "
                                                             f"port: {self.mqtt_config['port']}."))

        mqttcommon.configure_reconnect_delay(self.client,
                                             min_delay=self.mqtt_config['min_delay'],
                                             max_delay=self.mqtt_config['max_delay'])

        try:
            self.connect(self.mqtt_config['host'], self.mqtt_config['port'], self.mqtt_config['keepalive'])
        except Exception as exception:  # want to catch all pylint: disable=broad-exception-caught
            self.logger_queue.put(mqttcommon.Logger.create_entry(
                self.name, 'ERROR', None,
                f"MQTT connect failed with {type(exception)} and reason {exception}."))
            # Shut down the publishing thread, a bit of a hack.
            # The service will restart it, and stops WeeWX when the restart budget is spent.
            self.publisher.process = False
            return

        # Reconnection, and the CONNACK processing, is handled by paho's network loop thread.
        self.client.loop_start()

    def _config_tls(self, tls_dict):
        """ Configure TLS."""
        def format_error(option, value):
            return f"Invalid '{option}', {value}"

        mqttcommon.configure_tls(self.client, tls_dict, format_error=format_error)

    def publish_message(self, time_stamp, qos, retain, topic, data):  # pylint: disable=too-many-arguments
        """ Publish the message. """
        payload = data
        data_type = type(data)
        if data is not None and data_type not in (str, bytearray, int, float):
            payload = json.dumps(data)

        start_time = time.time()
        mqtt_message_info = self.client.publish(topic, payload, qos=qos, retain=retain)
        self.logger_queue.put(mqttcommon.Logger.create_entry(
            self.name, 'DEBUG', None,
            (f"At {int(time.time())}  publishing: {int(time_stamp)} "
             f" {mqtt_message_info.mid} {qos} {topic} took {time.time() - start_time}")))

        # Paho drops the message and returns an error when it is not connected (MQTT_ERR_NO_CONN)
        # or its outbound queue is full (MQTT_ERR_QUEUE_SIZE). Log it; there is nothing to retry.
        if mqtt_message_info.rc != mqtt.MQTT_ERR_SUCCESS:
            self.logger_queue.put(mqttcommon.Logger.create_entry(
                self.name, 'ERROR', None,
                (f"The publish of {topic} is not accepted with "
                 f"{mqtt.error_string(mqtt_message_info.rc)}, the message is dropped.")))

    def get_client(self, client_id, protocol):
        ''' Get the MQTT client. '''
        return mqttcommon.create_client(self.api,
                                        client_id=client_id,
                                        protocol=protocol,
                                        clean_session=True)

    def set_callbacks(self, log_mqtt):
        ''' Setup the MQTT callbacks. '''
        self.client.on_connect = mqttcommon.adapt_callback(self.api, 'on_connect', self.on_connect)
        self.client.on_disconnect = mqttcommon.adapt_callback(self.api, 'on_disconnect', self.on_disconnect)
        self.client.on_publish = mqttcommon.adapt_callback(self.api, 'on_publish', self.on_publish)
        self.client.on_message = self.on_message

        if log_mqtt:
            self.client.on_log = self.on_log

    def connect(self, host, port, keepalive):
        ''' Connect to the MQTT server. '''
        mqttcommon.connect(self.client, self.api, host=host, port=port, keepalive=keepalive, clean_start=True)

    def on_log(self, _client, _userdata, level, msg):
        """ The on_log callback. """
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.mqtt_logger.get(level, None), None, f"MQTT log: {msg}"))

    def on_connect(self, client, userdata, flags, rc, properties):  # pylint: disable=too-many-arguments
        """ The on_connect callback. """
        # https://pypi.org/project/paho-mqtt/#on-connect
        # rc:
        # 0: Connection successful
        # 1: Connection refused - incorrect protocol version
        # 2: Connection refused - invalid client identifier
        # 3: Connection refused - server unavailable
        # 4: Connection refused - bad username or password
        # 5: Connection refused - not authorised
        # 6-255: Currently unused.
        if int(rc) != 0:
            self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'ERROR', None,
                                                                 (f"Connection refused with result code {int(rc)}, "
                                                                  f"{mqtt.error_string(rc)}, flags {str(flags)}.")))
            return

        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'INFO', None,
                                                             f"Connected with result code {int(rc)}, {mqtt.error_string(rc)}"))

        self._handle_connect_success((client, userdata, flags, rc, properties))

    def on_disconnect(self, _client, _userdata, rc, _properties):
        """ The on_disconnect callback. """
        # https://pypi.org/project/paho-mqtt/#on-disconnect
        # The rc parameter indicates the disconnection state.
        # If MQTT_ERR_SUCCESS (0), the callback was called in response to a disconnect() call.
        # If any other value the disconnection was unexpected,
        # such as might be caused by a network error.
        self._handle_disconnect(rc)

    def on_publish(self, _client, _userdata, mid, _properties):
        """ The on_publish callback. """
        time_stamp = "          "
        qos = ""
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'DEBUG', None,
                                                             f"At {int(time.time())} published: {time_stamp} {mid} {qos}"))

    def _publish_lwt_online(self):
        """ Publish the LWT 'online' message, when lwt is configured. """
        if self.lwt_dict is not None and to_bool(self.lwt_dict.get('enable', True)):
            self.client.publish(topic=self.lwt_dict.get('topic', 'status'),
                                payload=self.lwt_dict.get('online_payload', 'online'),
                                qos=to_int(self.lwt_dict.get('qos', 0)),
                                retain=to_bool(self.lwt_dict.get('retain', True)))

    def _run_connect_callbacks(self, callback_args, timing):
        """ Run the on_mqtt_connect plugin callbacks for one timing group. """
        run_time = 0
        for plugin_name in self.plugin_manager.callbacks['on_mqtt_connect'][timing]:
            start_time = time.time()
            self.plugin_manager.callbacks['on_mqtt_connect'][timing][plugin_name](*callback_args)
            delta_time = time.time() - start_time
            run_time += delta_time
            self.logger_queue.put(mqttcommon.Logger.create_entry(
                self.name, self.monitor_on_connect, None,
                (f"monitor: {delta_time:<12.10f} on_connect ({timing}) {plugin_name}")))
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_on_connect, None,
                                                             (f"monitor: {run_time:<12.10f} on_connect ({timing})")))

    def _handle_connect_success(self, callback_args):
        """ The connection succeeded. Run the common processing.
            callback_args is the paho callback tuple: (client, userdata, flags, rc, properties). """
        flags = callback_args[2]
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'INFO', None, f"Connected flags {str(flags)}"))

        self._run_connect_callbacks(callback_args, 'immediate')

        self._publish_lwt_online()

        self._run_connect_callbacks(callback_args, 'delay')

        self.connected = True

    def _handle_disconnect(self, rc):
        """ The connection was lost, or a disconnect was requested. Mark as not connected. """
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'INFO' if int(rc) == 0 else 'ERROR', None,
                                                             f"Disconnected with result code {int(rc)}, {mqtt.error_string(rc)}"))

        # As of 1.6.1, Paho MQTT cannot have a callback invoke a second callback. So we won't reconnect here.
        # Because that would cause the on_connect callback to be called. Instead we will just mark as not connected.
        # Paho's network loop thread handles the reconnection.
        self.connected = False

    def on_message(self, client, userdata, msg):
        """ The on_message callback. """
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'DEBUG', None, f"Received: {userdata} {msg}"))

        run_time = 0
        for plugin_name in self.plugin_manager.callbacks['on_mqtt_message']['immediate']:
            start_time = time.time()
            self.plugin_manager.callbacks['on_mqtt_message']['immediate'][plugin_name](client, userdata, msg)
            delta_time = time.time() - start_time
            run_time += delta_time
            self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_on_message, None,
                                                                 (f"monitor: {delta_time:<12.10f} on_message (immediate) "
                                                                  f"{plugin_name}  {msg}")))
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_on_message, None,
                                                             (f"monitor: {run_time:<12.10f} on_message (immediate)")))

        run_time = 0
        for plugin_name in self.plugin_manager.callbacks['on_mqtt_message']['delay']:
            start_time = time.time()
            self.plugin_manager.callbacks['on_mqtt_message']['delay'][plugin_name](client, userdata, msg)
            delta_time = time.time() - start_time
            run_time += delta_time
            self.logger_queue.put(mqttcommon.Logger.create_entry(
                self.name, self.monitor_on_message, None,
                (f"monitor: {delta_time:<12.10f} on_message (delay) {plugin_name} {msg}")))

        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_on_message, None,
                                                             (f"monitor: {run_time:<12.10f} on_message (delay)")))

class PublishWeeWX():  # pylint: disable=too-few-public-methods
    """ Backwards compatibility class."""
    def __init__(self, engine, config_dict):
        self.mqtt_publish = MQTTPublish(engine, config_dict)

    def shutDown(self):  # NOSONAR - Needed for backward compatibility pylint: disable=invalid-name
        """Run when an engine shutdown is requested."""
        self.mqtt_publish.shutDown()

class MQTTPublish(StdService):  # pylint: disable=too-many-instance-attributes
    """ A service to publish WeeWX loop and/or archive data to MQTT. """
    def __init__(self, engine, config_dict):
        super().__init__(engine, config_dict)
        self.name = f"{self.__class__.__name__}-{threading.get_native_id()}"

        service_dict = config_dict.get('MQTTPublish', {})

        # The logger starts the thread that logs queued messages, so its queue has to exist first.
        self.multiprocess = to_bool(service_dict.get('multiprocess', False))
        self.logger_queue = self._create_logger_queue()

        self.logger = mqttcommon.Logger(self.name, self.logger_queue, log_name=__name__)

        self.logger.info(None, f"MQTTPublish version: {VERSION}.")

        self.plugins = self._configure_plugins(config_dict, service_dict)

        exclude_keys = ['password']
        sanitized_service_dict = {k: service_dict[k] for k in set(service_dict.keys()) - set(exclude_keys)}
        self.logger.debug(None, f"sanitized configuration removed {exclude_keys}")
        self.logger.debug(None, f"sanitized_service_dict is {sanitized_service_dict}")

        #  backwards compatibility
        if 'PublishWeeWX' in service_dict.sections:
            self.logger.error(None, "'PublishWeeWX' is deprecated. Move options to top level, '[MQTTPublish]'.")
            service_dict = config_dict.get('MQTTPublish', {}).get('PublishWeeWX', {})

        self.enable = to_bool(service_dict.get('enable', True))
        if not self.enable:
            self.logger.info(None, "Not enabled, exiting.")
            return

        data_binding = service_dict.get('data_binding', 'wx_binding')
        self.manager_dict = weewx.manager.get_manager_dict_from_config(config_dict, data_binding)

        self.weewx_dict = self._configure_weewx_dict(engine, config_dict)

        self.topics_loop, self.topics_archive, binding = self.configure_topics(service_dict)
        self.logger.debug(None, f"archive topic configuration is: {self.topics_archive}")
        self.logger.debug(None, f"loop topic configuration is: {self.topics_loop}")

        self.mqtt_config, self.monitor_config = self._configure_mqtt(service_dict)

        self.max_thread_restarts = to_int(service_dict.get('max_thread_restarts', 2))
        self.thread_restarts = 0

        self.wait_for_thread_shutdown = to_int(service_dict.get('wait_for_thread_shutdown', 10))

        self._log_deprecated_options(service_dict)

        self.data_queue = Queue.Queue()
        # Everything the queue processor needs, other than the queues it reads from and logs to.
        self.processor_config = {
            'plugins': self.plugins,
            'weewx_dict': self.weewx_dict,
            'manager_dict': self.manager_dict,
            'mqtt_config': self.mqtt_config,
            'monitor_config': self.monitor_config,
            'topics_loop': self.topics_loop,
            'topics_archive': self.topics_archive,
        }
        if self.multiprocess:
            self._thread = PublishWeeWXProcess(self.logger_queue,
                                               self.data_queue,
                                               self.processor_config)
        else:
            self._thread = PublishWeeWXThread(self.logger_queue,
                                              self.data_queue,
                                              self.processor_config)

        self.thread_start()

        if 'archive' in binding:
            self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

        if 'loop' in binding:
            self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)

    def _create_logger_queue(self):
        """ Create the queue the LoggerThread drains.
            In multiprocess mode it has to be a multiprocessing.Queue, the queue processor
            puts into it from a child process. """
        if self.multiprocess:
            return multiprocessing.Queue()

        return Queue.Queue()

    def _configure_plugins(self, config_dict, service_dict):
        """ Configure the plugins. """
        plugins = service_dict.get('plugins', [])
        if isinstance(plugins, dict):
            self.logger.error(None,
                              ("'[[plugins]]' is deprecated. "
                               "To configure see, https://weewx-mqtt.github.io/publish/plugins/"))
            return plugins

        self.logger.info(None, f"The plugins are: {plugins}")
        configured_plugins = configobj.ConfigObj({})
        for plugin in to_list(plugins):
            if plugin not in config_dict:
                self.logger.error(None, f"{plugin} is missing its configuration section.")
            else:
                configured_plugins[plugin] = config_dict[plugin]
        return configured_plugins

    def _configure_weewx_dict(self, engine, config_dict):
        """ Configure the weewx dictionary that is handed to the plugins. """
        weewx_dict = {}
        # ToDo: Fix this hack to get more information to certain plugins
        weewx_dict['engine'] = engine
        weewx_dict['config_dict'] = config_dict
        weewx_dict['stn_info'] = engine.stn_info
        weewx_dict['manager_dict'] = self.manager_dict
        weewx_dict['defaults'] = weeutil.config.deep_copy(weewx.defaults.defaults)
        weewx_dict['defaults'].interpolation = False
        if 'Defaults' in config_dict.get('StdReport', {}):
            weeutil.config.merge_config(weewx_dict['defaults'], config_dict['StdReport']['Defaults'])
        return weewx_dict

    def _log_deprecated_options(self, service_dict):
        """ Warn about options that are deprecated and no longer used. """
        if 'binding' in service_dict:
            self.logger.info(None, "'binding' is deprecated and no longer used.")

        for option in ('max_retries', 'wait_between_retries', 'wait_for_connection'):
            if option in service_dict:
                self.logger.info(None, f"'{option}' is deprecated and no longer used.")

    def _configure_mqtt(self, service_dict):
        """ Configure the mqtt connection and monitoring options. """
        mqtt_config = {}
        mqtt_config['keepalive'] = to_int(service_dict.get('keepalive', 60))
        mqtt_config['wait_for_queue_element'] = to_int(service_dict.get('wait_for_queue_element', 5))
        mqtt_config['min_delay'] = to_int(service_dict.get('min_delay', 1))
        mqtt_config['max_delay'] = to_int(service_dict.get('max_delay', 120))

        mqtt_config['log_mqtt'] = to_bool(service_dict.get('log_mqtt', False))
        mqtt_config['host'] = service_dict.get('host', 'localhost')
        mqtt_config['port'] = to_int(service_dict.get('port', 1883))
        mqtt_config['username'] = service_dict.get('username', None)
        mqtt_config['password'] = service_dict.get('password', None)
        mqtt_config['clientid'] = service_dict.get('clientid', 'MQTTPublish-' +
                                                   str(random.randint(1000, 9999)))  # NOSONAR - just need a unique id

        protocol_string = service_dict.get('protocol', 'MQTTv311')
        mqtt_config['protocol'] = getattr(mqtt, protocol_string, 0)

        mqtt_config['tls'] = service_dict.get('tls')
        mqtt_config['lwt'] = service_dict.get('lwt')
        if mqtt_config['lwt'] is not None:
            self.logger.error(None, "'[[lwt]]' is deprecated.  use [[availability_topic]].")
        else:
            mqtt_config['lwt'] = service_dict.get('availability_topic', {})

        exclude_keys = ['password']
        sanitized_mqtt_config = {k: mqtt_config[k] for k in set(mqtt_config.keys()) - set(exclude_keys)}
        self.logger.debug(None, f"sanitized mqtt_config removed {exclude_keys}")
        self.logger.debug(None, f"sanitized_mqtt_config is {sanitized_mqtt_config}")

        monitor_config = {
            'monitor_queue': service_dict.get('monitor_queue'),
            'monitor_record_update': service_dict.get('monitor_record_update'),
            'monitor_on_weewx_data': service_dict.get('monitor_on_weewx_data'),
            'monitor_on_message': service_dict.get('monitor_on_message'),
            'monitor_on_connect': service_dict.get('monitor_on_connect'),
        }
        return mqtt_config, monitor_config

    def configure_fields(self, fields_dict, field_defaults):
        """ Configure the fields. """
        fields = {}
        if fields_dict:
            for field in fields_dict.sections:
                fields[field] = {}
                field_dict = fields_dict.get(field, {})
                fields[field]['name'] = field_dict.get('name', field)
                fields[field]['unit'] = field_dict.get('unit', None)

                fields[field]['ignore'] = to_bool(field_dict.get('ignore', field_defaults['ignore']))
                fields[field]['publish_none_value'] = to_bool(
                    field_dict.get('publish_none_value', field_defaults['publish_none_value']))
                fields[field]['append_unit_label'] = to_bool(
                    field_dict.get('append_unit_label', field_defaults['append_unit_label']))
                fields[field]['conversion_type'] = field_dict.get('conversion_type', field_defaults['conversion_type'])
                fields[field]['round'] = to_int(field_dict.get('round', field_defaults['round']))
                fields[field]['format_string'] = field_dict.get('format_string', field_defaults['format_string'])

        return fields

    def configure_topics(self, service_dict):
        """ Configure the topics. """

        if 'topics' not in service_dict:
            raise ValueError("[[topics]] is required.")

        topics_loop = {}
        topics_archive = {}
        event_binding = {}
        for topic in service_dict['topics'].sections:
            loop_config, archive_config = self._configure_topic(service_dict, topic)
            if loop_config is not None:
                topics_loop[topic] = loop_config
                event_binding['loop'] = True

            if archive_config is not None:
                topics_archive[topic] = archive_config
                event_binding['archive'] = True

        self.logger.debug(None, f"Loop topics: {topics_loop}")
        self.logger.debug(None, f"Archive topics: {topics_archive}")
        return topics_loop, topics_archive, event_binding.keys()

    def _configure_topic(self, service_dict, topic):
        """ Resolve one topic, returning its (loop, archive) configs, or (None, None) when unpublished. """
        topic_dict = service_dict['topics'].get(topic, {})
        field_options = self._resolve_field_options(service_dict, topic_dict)
        topic_options = self._resolve_topic_options(service_dict, topic_dict)

        fields = self._configure_topic_fields(field_options, topic_dict.get('fields', None))
        self._apply_field_list_overrides(topic_dict, fields)
        self._configure_deprecated_aggregates(topic, topic_dict.get('aggregates', {}))

        # ToDo: add a check that ignore_field and publish_field are mutually exclusive
        # ToDo: Could go as far making sure there are no fully configured fields...

        if not topic_options['publish']:
            return None, None

        loop_config = None
        archive_config = None
        if 'loop' in topic_options['binding']:
            self.logger.info(None, f"Publishing to {topic} for loop data.")
            loop_config = self._build_topic_config(topic_options, field_options, fields)

        if 'archive' in topic_options['binding']:
            self.logger.info(None, f"Publishing to {topic} for archive data.")
            archive_config = self._build_topic_config(topic_options, field_options, fields)

        return loop_config, archive_config

    @staticmethod
    def _resolve_field_options(service_dict, topic_dict):
        """ Resolve the field level options, applying the service level defaults. """
        return {
            # These are field level options that can have default options at the topic level
            'ignore': to_bool(topic_dict.get('ignore', False)),
            'publish_none_value': to_bool(topic_dict.get('publish_none_value', False)),
            # These are field level options that have default options above the topic level
            'append_unit_label': to_bool(topic_dict.get('append_unit_label', service_dict.get('append_unit_label', True))),
            'conversion_type': topic_dict.get('conversion_type', service_dict.get('conversion_type', 'string')),
            'round': to_int(topic_dict.get('round', service_dict.get('round', None))),
            'format_string': topic_dict.get('format_string', service_dict.get('format_string', None)),
        }

    @staticmethod
    def _resolve_topic_options(service_dict, topic_dict):
        """ Resolve the topic level options, applying the service level defaults. """
        minimum_interval = to_int(topic_dict.get('minimum_interval', service_dict.get('minimum_interval', 0)))
        return {
            'publish': to_bool(topic_dict.get('publish', True)),
            'binding': weeutil.weeutil.option_as_list(topic_dict.get('binding', ['archive', 'loop'])),
            'unit_system': weewx.units.unit_constants[topic_dict.get('unit_system',
                                                                     service_dict.get('unit_system', 'US'))],
            # These are topic level options that can have default options
            'qos': to_int(topic_dict.get('qos', service_dict.get('qos', 0))),
            'minimum_interval': minimum_interval * 60,
            'suppression_threshold': to_float(
                topic_dict.get('suppression_threshold', service_dict.get('suppression_threshold', 0))),
            'retain': to_bool(topic_dict.get('retain', service_dict.get('retain', False))),
            'type': topic_dict.get('type', service_dict.get('type', 'json')),
        }

    def _configure_topic_fields(self, field_options, fields_dict):
        """ Configure the topic fields. """
        if fields_dict is None:
            return {}
        return self.configure_fields(fields_dict, field_options)

    @staticmethod
    def _build_topic_config(topic_options, field_options, fields):
        """ Build the topic configuration. """
        return {
            'qos': topic_options['qos'],
            'minimum_interval': topic_options['minimum_interval'],
            'suppression_threshold': topic_options['suppression_threshold'],
            'retain': topic_options['retain'],
            'type': topic_options['type'],
            'unit_system': topic_options['unit_system'],
            'ignore': field_options['ignore'],
            'append_unit_label': field_options['append_unit_label'],
            'conversion_type': field_options['conversion_type'],
            'round': field_options['round'],
            'format_string': field_options['format_string'],
            'fields': dict(fields),
            'data_last_published': {},
        }

    @staticmethod
    def _apply_field_list_overrides(topic_dict, fields):
        """ Apply the deprecated ignore_fields and publish_fields options. """
        for ignore_field in to_list(topic_dict.get('ignore_fields', [])):
            fields[ignore_field] = {
                'ignore': True
            }

        for publish_field in to_list(topic_dict.get('publish_fields', [])):
            fields[publish_field] = {
                'ignore': False
            }

    def _configure_deprecated_aggregates(self, topic, aggregates):
        """ Convert a deprecated '[aggregates]' stanza to the MQTTAggregateValues plugin configuration. """
        if not aggregates:
            return

        # Temporarily build the MQTTAggregateValues plugin configuration
        self.logger.error(None,
                          ("'[aggregates]' is deprecated and has moved to a plugin. "
                           "To configure see, https://weewx-mqtt.github.io/publish/plugins/aggregatevalues/"))
        if 'MQTTAggregateValues' not in self.plugins:
            self.plugins['MQTTAggregateValues'] = {}
            self.plugins['MQTTAggregateValues']['module'] = 'user.mqttaggregatevalues'
        if 'topics' not in self.plugins['MQTTAggregateValues']:
            self.plugins['MQTTAggregateValues']['topics'] = {}
        if topic not in self.plugins['MQTTAggregateValues']['topics']:
            self.plugins['MQTTAggregateValues']['topics'][topic] = {}
        for aggregate in aggregates:
            self.plugins['MQTTAggregateValues']['topics'][topic][aggregate] = aggregates[aggregate]

    def thread_start(self):
        """Start the publishing thread."""
        self.logger.info(None, "Starting up queue processor.")
        self._thread.start()

        if not self._thread.is_alive():
            raise weewx.WakeupError("Unable to start MQTT publishing thread.")

    def new_loop_packet(self, event):
        """ Handle loop packets. """
        self._handle_record('loop', copy.deepcopy(event.packet))

    def new_archive_record(self, event):
        """ Handle archive records. """
        self._handle_record('archive', copy.deepcopy(event.record))

    def _handle_record(self, data_type, data):
        """ Queue a record for publishing, restarting the thread if it has died. """
        self._check_queue_backlog()

        if not self._thread.is_alive():
            self._restart_thread(data_type, data)
            return

        self.data_queue.put({'time_stamp': data.get('dateTime', time.time()),
                             'type': data_type,
                             'data': data})
        self._log_input_queue_size()

        # A bit of a hack. The thread is running and the MQTT client is connected.
        # So, we will reset the restart count.
        if self._thread.processor.publisher and self._thread.processor.publisher.connected:
            self.thread_restarts = 0

    def _check_queue_backlog(self):
        """ Log an error when the input queue is filling up. """
        queue_size = self.data_queue.qsize()
        if queue_size > 0 and queue_size % 10 == 0:
            self.logger.error(None, f"Data queue has size of {self.data_queue.qsize()}.")

    def _restart_thread(self, data_type, data):
        """ Replace a dead publishing thread, or give up when the restart budget is spent. """
        if self.thread_restarts >= self.max_thread_restarts:
            raise weewx.StopNow("MQTT publishing thread has stopped.")

        self.thread_restarts += 1
        if self.multiprocess:
            self._thread = PublishWeeWXProcess(self.logger_queue, self.data_queue, self.processor_config)
        else:
            self._thread = PublishWeeWXThread(self.logger_queue, self.data_queue, self.processor_config)
        self._thread.daemon = True

        self.thread_start()

        # A time stamp is required here: the replacement thread has not seen this record yet.
        self.data_queue.put({'time_stamp': data['dateTime'], 'type': data_type, 'data': data})
        self._log_input_queue_size()

    def _log_input_queue_size(self):
        """ Log the input queue size under the queue monitor flag. """
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_config['monitor_queue'], None,
                                                             f"monitor: Input queue size: {self.data_queue.qsize()}"))

    def shutDown(self):
        """Run when an engine shutdown is requested."""
        self.logger.info(None, "Shutdown initiated")
        self._shut_down_publishing()
        self._shut_down_logger()

    def _shut_down_publishing(self):
        """Stop the publishing thread, if one is running."""
        if not self._thread:
            return

        self.logger.info(None, f"Emptying data queue with size of {self.data_queue.qsize()}.")
        self._drain_data_queue()
        self.logger.info(None, f"Data queue has size of {self.data_queue.qsize()}.")
        self.logger.info(None, "Shutdown of queue processor initiated")
        self.data_queue.put({'time_stamp': time.time(), 'type': 'shutdown', 'data': {}})

        self._wait_for_thread(self._thread)
        self._thread = None

    def _shut_down_logger(self):
        """Stop the thread that hands log records over to the WeeWX logger."""
        self.logger.info(None, f"Shutdown of logger thread, {self.logger.log_thread.name} initiated")
        self.logger.shutdown(self.wait_for_thread_shutdown)

    def _drain_data_queue(self):
        """Take items off the data queue until a get times out on an empty queue."""
        while self._drain_one_item():
            pass

    def _drain_one_item(self):
        """Take one item. Returns False once the queue is empty.

        Another process may already be performing the get operation and, without
        time to acquire the lock for exclusive access, Queue.Empty is raised even
        though the queue is not empty. So an Empty is only conclusive when the
        queue also reports itself empty.
        https://github.com/python/cpython/issues/87302#issuecomment-3659919391
        """
        try:
            self.data_queue.get(timeout=0.05)
        except Queue.Empty:
            return bool(self.data_queue.qsize())
        return True

    def _wait_for_thread(self, thread, message_suffix=""):
        """Wait for a thread to stop, warning when it does not."""
        thread.join(self.wait_for_thread_shutdown)
        if thread.is_alive():
            self.logger.error(None, f"Unable to shut down {thread.name}{message_suffix}")


class QueueProcessor(multiprocessing.Process):  # pylint: disable=too-many-instance-attributes
    """Publish WeeWX data to MQTT. """
    # For some reason, when PublishWeeWXProcess was a process, getting data from the Queue would lock.
    # The locks seemed to random. I tried all types of multiprocessing queues and Pipe (send/recv).
    # Changing PublishWeeWXProcess to a thread that re-queues the data for this process seems to have fixed it.
    # Note, PublishWeeWXThread calls this class's run method directly, avoiding the overhead of the extra queue.
    # The queueing problem was on Ubuntu 22.04 and python 3.10.13
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
                 logger_queue,
                 data_queue,
                 processor_config):
        # processor_config holds: plugins, weewx_dict, manager_dict,
        #                         mqtt_config, monitor_config, topics_loop, topics_archive
        multiprocessing.Process.__init__(self)
        self.name = f"{self.__class__.__name__}-{threading.get_native_id()}"

        self.logger_queue = logger_queue
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'INFO', None, "Initializing queue processor."))

        self.start_time = 0

        self.monitor_config = processor_config['monitor_config']
        self.monitor_queue = self.monitor_config['monitor_queue']
        self.monitor_record_update = self.monitor_config['monitor_record_update']
        self.monitor_on_weewx_data = self.monitor_config['monitor_on_weewx_data']

        self.plugins = processor_config['plugins']
        self.weewx_dict = processor_config['weewx_dict']
        self.manager_dict = processor_config['manager_dict']
        self.publisher = None

        self.db_manager = None
        self.plugin_manager = None

        self.mqtt_config = processor_config['mqtt_config']
        self.topics_loop = processor_config['topics_loop']
        self.topics_archive = processor_config['topics_archive']
        self.all_topics = {**self.topics_loop, **self.topics_archive}
        self.lwt_dict = self.mqtt_config.get('lwt')

        self.data_queue = data_queue

        # Flag to control thread running.
        # Setting to False will stop the thread.
        # ToDo: eliminate?
        self.process = True

    def profile(self, msg):
        """ Log the profiling data. """
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'INFO', None, msg))

    def update_record(self, topic_dict, _time_stamp, record):
        """ Update the record. """
        final_record = {}
        interval_end = self._minimum_interval_end(topic_dict)
        updated_record = weewx.units.to_std_system(record, topic_dict['unit_system'])

        publish_interval_end_ts = False
        for field in updated_record:
            (new_interval, updates) = self._update_field(topic_dict, updated_record, field, interval_end)
            final_record.update(updates)
            publish_interval_end_ts = publish_interval_end_ts or new_interval

        if final_record and interval_end is not None and publish_interval_end_ts:
            final_record['interval_end_ts'] = interval_end

        return final_record

    @staticmethod
    def _minimum_interval_end(topic_dict):
        """ Get the end of the current minimum interval, if there is one. """
        if topic_dict['minimum_interval']:
            return startOfInterval(time.time(), topic_dict['minimum_interval']) + topic_dict['minimum_interval']
        return None

    def _update_field(self, topic_dict, updated_record, field, interval_end):
        """ Update one field of the record.

        Returns a (new_interval, updates) tuple, where updates holds the
        fields to publish and new_interval is True when the field advanced
        to a new minimum interval.
        """
        fieldinfo = topic_dict['fields'].get(field, {})
        if fieldinfo.get('ignore', topic_dict.get('ignore')):
            return False, {}

        value = updated_record[field]
        publish_none_value = fieldinfo.get('publish_none_value', topic_dict.get('publish_none_value'))
        if value is None and not publish_none_value:
            return False, {}

        (name, updated_value) = self.update_field(topic_dict,
                                                  fieldinfo,
                                                  field,
                                                  value,
                                                  updated_record['usUnits'])
        threshold = fieldinfo.get('suppression_threshold', topic_dict.get('suppression_threshold'))

        last_published = topic_dict['data_last_published'].get(name, {})
        last_published_timestamp = last_published.get('interval_end')

        new_interval = interval_end is None or last_published_timestamp is None or interval_end > last_published_timestamp

        updates = {}
        if self._should_publish_value(new_interval, updated_value, last_published.get('value'), threshold):
            updates[name] = self._format_value(topic_dict, fieldinfo, updated_value)
            topic_dict['data_last_published'][name] = {
                'value': updated_value,
                'interval_end': interval_end,
            }

        return new_interval, updates

    @staticmethod
    def _should_publish_value(new_interval, value, last_published_value, threshold):
        """ Decide whether the value should be published. """
        # Either value or last_published_value is None, but not both nor neither.
        is_none = (value is None) != (last_published_value is None)
        # A None value has no magnitude to compare against the suppression threshold.
        # So publish it when it appears or disappears, but not on every record.
        if new_interval or is_none:
            return True
        if value is None or last_published_value is None:
            return False
        return value < last_published_value - threshold or value > last_published_value + threshold

    @staticmethod
    def _format_value(topic_dict, fieldinfo, value):
        """ Format the value, if a format string is configured. """
        format_string = fieldinfo.get('format_string', topic_dict.get('format_string'))
        if format_string is not None and value is not None:
            return format_string % value
        return value

    @staticmethod
    def update_field(topic_dict, fieldinfo, field, value, unit_system):
        """ Update field. """
        name = fieldinfo.get('name', field)
        if fieldinfo.get('append_unit_label', topic_dict.get('append_unit_label')):
            name = QueueProcessor._append_unit_label(name, fieldinfo.get('unit'), unit_system)

        converted_value = QueueProcessor._convert_unit(fieldinfo, field, value, unit_system)

        conversion_type = fieldinfo.get('conversion_type', topic_dict.get('conversion_type'))
        round_amount = fieldinfo.get('round', topic_dict.get('round'))
        converted_value = QueueProcessor._coerce_value(converted_value, conversion_type, round_amount)

        return name, converted_value

    @staticmethod
    def _append_unit_label(name, unit, unit_system):
        """ Return the name with the field's unit label appended, when it has one. """
        if unit is None:
            (unit_type, _) = weewx.units.getStandardUnitType(unit_system, name)
        else:
            unit_type = unit
        unit_type = QueueProcessor.UNIT_REDUCTIONS.get(unit_type, unit_type)
        if unit_type is None:
            return name
        return f"{name}_{unit_type}"

    @staticmethod
    def _convert_unit(fieldinfo, field, value, unit_system):
        """ Convert the value to the configured unit, or pass it through untouched. """
        unit = fieldinfo.get('unit')
        if unit is None:
            return value
        (from_unit, from_group) = weewx.units.getStandardUnitType(unit_system, field)
        return weewx.units.convert((value, from_unit, from_group), unit)[0]

    @staticmethod
    def _coerce_value(value, conversion_type, round_amount):
        """ Apply the configured type conversion, then the configured rounding. """
        if conversion_type == 'integer':
            value = to_int(value)
        elif conversion_type == 'float':
            value = to_float(value)

        if round_amount and isinstance(value, float):
            value = round(value, round_amount)
        return value

    def publish_row(self, time_stamp, data, topics):
        """ Publish the data. """
        immediate_time = 0
        delay_time = 0
        process_time = time.time()
        for topic in topics:
            record = copy.deepcopy(data)
            run_time = 0
            for plugin_name in self.publisher.plugin_manager.callbacks['update_record']['immediate']:
                start_time = time.time()
                self.publisher.plugin_manager.callbacks['update_record']['immediate'][plugin_name](self.publisher.client,
                                                                                                   topic,
                                                                                                   record,
                                                                                                   data['usUnits'],
                                                                                                   topics[topic]['qos'],
                                                                                                   topics[topic]['retain'])
                delta_time = time.time() - start_time
                run_time += delta_time
                self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_record_update, None,
                                                                     (f"monitor: {delta_time:<12.10f} update_record (immediate) "
                                                                      f"{topic} for {plugin_name}")))

            self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_record_update, None,
                                                                 (f"monitor: {run_time:<12.10f} update_record (immediate) {topic}")))
            immediate_time += run_time

            start_time = time.time()
            updated_record = self.update_record(topics[topic], time_stamp, record)
            self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_record_update, None,
                                                                 (f"monitor: {(time.time() - start_time):<12.10f} "
                                                                  f"update_record (update_record) {topic}")))

            run_time = 0
            for plugin_name in self.publisher.plugin_manager.callbacks['update_record']['delay']:
                # Note, this is called with the unit_system from the configuration because:
                # 1. The record has been converted to this unit_system
                # 2. The record may not be publishing the field usUnits.
                # self.profile(f"  profile: before delay update_record {time.time() - self.start_time} {topic} {plugin_name}")
                start_time = time.time()
                self.publisher.plugin_manager.callbacks['update_record']['delay'][plugin_name](self.publisher.client,
                                                                                               topic,
                                                                                               updated_record,
                                                                                               topics[topic]['unit_system'],
                                                                                               topics[topic]['qos'],
                                                                                               topics[topic]['retain'])
                delta_time = time.time() - start_time
                run_time += delta_time
                self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_record_update, None,
                                                                     (f"monitor: {delta_time:<12.10f} update_record (delay) "
                                                                      f"{topic} for {plugin_name}")))
            self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_record_update, None,
                                                                 (f"monitor: {run_time:<12.10f} update_record (delay) {topic}")))
            delay_time += run_time

            start_time = time.time()
            self.publish_record(time_stamp, topic, topics[topic], updated_record)
            self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_record_update, None,
                                                                 (f"monitor: {(time.time() - start_time):<12.10f} "
                                                                  f"update_record (publish_message) {topic} ")))

        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_record_update, None,
                                                             (f"monitor: {immediate_time:<12.10f} update_record (immediate)")))
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_record_update, None,
                                                             (f"monitor: {delay_time:<12.10f} update_record (delay)")))

        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_record_update, None,
                                                             (f"monitor: {(time.time() - process_time):<12.10f} "
                                                              f"update_record (publish_row total)")))

    def publish_record(self, time_stamp, topic, topic_dict, updated_record):
        """ Publish an updated record, using the topic's configured type. """
        if not updated_record:
            return

        if topic_dict['type'] == 'json':
            self.publisher.publish_message(time_stamp,
                                           topic_dict['qos'],
                                           topic_dict['retain'],
                                           topic,
                                           json.dumps(updated_record))
        if topic_dict['type'] == 'keyword':
            data_keyword = ', '.join(f"{key}={val}" for (key, val) in updated_record.items())
            self.publisher.publish_message(time_stamp,
                                           topic_dict['qos'],
                                           topic_dict['retain'],
                                           topic,
                                           data_keyword)
        if topic_dict['type'] == 'individual':
            for key, value in updated_record.items():
                self.publisher.publish_message(time_stamp,
                                               topic_dict['qos'],
                                               topic_dict['retain'],
                                               topic + '/' + key,
                                               value)

    def run(self):
        """ Process the queue. """
        threading.current_thread().name = f"MQTTPublish-{threading.get_native_id()}"

        self.create_plugins()

        # need to instantiate inside thread
        self.publisher = Publisher(self.logger_queue,
                                   self.plugin_manager,
                                   self, self.mqtt_config,
                                   self.monitor_config)

        with weewx.manager.open_manager(self.manager_dict) as db_manager:
            self.db_manager = db_manager
            self.process_queue()

        # MQTT's LWT is sent from the broker on an unexpected disconnect.
        # So we need to send an offline message on an 'expected' disconnect.
        if self.lwt_dict is not None and to_bool(self.lwt_dict.get('enable', True)):
            self.publisher.client.publish(topic=self.lwt_dict.get('topic', 'status'),
                                          payload=self.lwt_dict.get('offline_payload', 'offline'),
                                          qos=to_int(self.lwt_dict.get('qos', 0)),
                                          retain=to_bool(self.lwt_dict.get('retain', True)))

        self.publisher.client.disconnect()
        # Stop paho's network loop thread. It must outlive the disconnect, so the DISCONNECT gets sent.
        self.publisher.client.loop_stop()
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'INFO', None, "Queue processor is shut down."))

    def create_plugins(self):
        """ Create the plugin manager and instantiate each configured plugin. """
        self.plugin_manager = PluginManager(self.logger_queue,
                                            self.monitor_config,
                                            self.mqtt_config,
                                            self.all_topics,
                                            self.weewx_dict)
        for plugin in self.plugins:
            if 'module' in self.plugins[plugin]:
                plugin_name = self.plugins[plugin]['module'] + '.' + plugin
            else:
                plugin_name = self.plugins[plugin]['plugin']
            self.plugin_manager.create_plugin(plugin, plugin_name, self.plugins[plugin])

    def process_queue(self):
        """ Pull items off the queue and process them until asked to shut down. """
        prev_time = time.time()
        while self.process:
            try:
                data2 = self.data_queue.get(block=True, timeout=self.mqtt_config['wait_for_queue_element'])
                prev_time = self.handle_queue_item(data2, prev_time)
                if prev_time is None:
                    break
            except Queue.Empty:
                self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_queue, None,
                                                                     (f"monitor: Queue is empty. "
                                                                      f"Waiting {self.mqtt_config['wait_for_queue_element']}")))

    def handle_queue_item(self, data2, prev_time):
        """ Process one queue item.

        Returns the new previous time, or None when the processor is shutting down.
        """
        data_type = data2['type']
        if data_type == 'shutdown':
            self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'INFO', None, "Shutting down queue processor."))
            self.process = False
            return None

        queue_size = self.data_queue.qsize()
        data2['queue_size'] = queue_size
        curr_time = time.time()
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_queue, None,
                                                             (f"monitor: Queue size: {queue_size} "
                                                              f"Process time: {curr_time - prev_time}")))

        self.on_weewx_data_immediate(data2)

        time_stamp = data2['time_stamp']
        data = data2['data']
        if data_type == 'loop':
            self.publish_row(time_stamp, data, self.topics_loop)
        elif data_type == 'archive':
            self.publish_row(time_stamp, data, self.topics_archive)
        else:
            self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'ERROR', None, f"Unknown data type, {data_type}"))

        self.on_weewx_data_delay(data2)

        return curr_time

    def on_weewx_data_immediate(self, data2):
        """ Run the 'immediate' on_weewx_data plugin callbacks. """
        run_time = 0
        for plugin_name in self.plugin_manager.callbacks['on_weewx_data']['immediate']:
            start_time = time.time()
            self.plugin_manager.callbacks['on_weewx_data']['immediate'][plugin_name](data2)
            delta_time = time.time() - start_time
            run_time += delta_time
            self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_on_weewx_data, None,
                                                                 (f"monitor: {delta_time:<12.10f} on_weewx_data (immediate) "
                                                                  f"{plugin_name}")))
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_on_weewx_data, None,
                                                             (f"monitor: {run_time:<12.10f} on_weewx_data (immediate)")))

    def on_weewx_data_delay(self, data2):
        """ Run the 'delay' on_weewx_data plugin callbacks. """
        run_time = 0
        for plugin_name in self.plugin_manager.callbacks['on_weewx_data']['delay']:
            start_time = time.time()
            self.plugin_manager.callbacks['on_weewx_data']['delay'][plugin_name](data2)
            delta_time = time.time() - start_time
            run_time += delta_time
            self.logger_queue.put(mqttcommon.Logger.create_entry(
                self.name, self.monitor_on_weewx_data, None,
                f"monitor: {delta_time:<12.10f} on_weewx_data (delay) {plugin_name}"))
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_on_weewx_data, None,
                                                             (f"monitor: {run_time:<12.10f} on_weewx_data (delay) "
                                                              f"")))

class PublishWeeWXThread(threading.Thread):
    """Publish WeeWX data to MQTT. """
    def __init__(self,
                 logger_queue,
                 data_queue,
                 processor_config):
        threading.Thread.__init__(self)
        self.name = f"{self.__class__.__name__}-{threading.get_native_id()}"

        self.logger_queue = logger_queue
        self.processor = QueueProcessor(self.logger_queue,
                                        data_queue,
                                        processor_config)

    def run(self):
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'INFO', None, f"Starting queue thread,  {self.name}."))

        self.processor.run()
        self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'INFO', None, f"Exited queue thread, {self.name}."))

class PublishWeeWXProcess(threading.Thread):
    """Publish WeeWX data to MQTT. """
    def __init__(self,
                 logger_queue,
                 data_queue,
                 processor_config):
        threading.Thread.__init__(self)
        self.name = f"{self.__class__.__name__}-{threading.get_native_id()}"

        self.logger_queue = logger_queue
        self.data_queue = data_queue
        self.monitor_config = processor_config['monitor_config']
        self.out_queue = multiprocessing.JoinableQueue()
        self.processor = QueueProcessor(self.logger_queue,
                                        self.out_queue,
                                        processor_config)
        self.processor.start()

    def run(self):
        while True:
            data = self.data_queue.get(block=True, timeout=None)
            self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_config['monitor_queue'], None,
                                                                 f"monitor: Input-2 queue size: {self.data_queue.qsize()}"))
            self.out_queue.put(data)
            if data['type'] == 'shutdown':
                self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, 'INFO', None, "Shutting down queue processor."))
                break
            self.logger_queue.put(mqttcommon.Logger.create_entry(self.name, self.monitor_config['monitor_queue'], None,
                                                                 f"monitor: Output queue size: {self.out_queue.qsize()}"))

        # Shutdown has been passed into queue processor
        # so wait for it to shut down
        if self.processor:
            self.processor.join(5)  # ToDo: make configurable
            if self.processor.is_alive():
                self.logger_queue.put(mqttcommon.Logger.create_entry(
                    self.name, 'ERROR', None, f"Unable to shut down {self.processor.name}"))

if __name__ == "__main__":
    import argparse

    def main():  # pragma: no cover  # noqa: CCR001
        """ Run it. """
        parser = argparse.ArgumentParser()
        parser.add_argument('--version', action='version', version=f'%(prog)s {VERSION}')

        parser.add_argument("--messages", required=True, type=str, dest="message_file",
                            help="The file with the test messages")

        parser.add_argument("--max-loops", type=int, default=5,
                            help="The maximum number of 'wait loops' for the thread processing to terminate.")

        parser.add_argument("config_file")

        options = parser.parse_args()

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

        with open(options.message_file, encoding='UTF-8') as file_object:
            packets = json.load(file_object)

        for packet in packets:
            for key in packet.keys():
                obs = packet[key]
                if isinstance(obs, str) and obs.lower() == 'none':
                    packet[key] = None
            new_loop_packet_event = weewx.Event(weewx.NEW_LOOP_PACKET, packet=packet)
            engine.dispatchEvent(new_loop_packet_event)

        loop_count = 0
        while loop_count < options.max_loops:
            print("sleeping")
            time.sleep(1)
            loop_count += 1

        mqtt_publish.shutDown()

    main()

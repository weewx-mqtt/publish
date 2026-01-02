#    Copyright (c) 2025 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

"""
Publish to MQTT on loop or archive creation.
"""

import queue as Queue

import abc
import datetime
import json
import logging
import random
import ssl
import threading
import time
import traceback

import configobj
import paho.mqtt.client as mqtt

import weeutil
from weeutil.weeutil import to_bool, to_float, to_int, TimeSpan

import weewx
from weewx.engine import StdService

VERSION = "1.0.0-rc02a"

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
        self.log.debug(msg)

    def loginf(self, msg):
        """ log informational messages """
        self.log.info(msg)

    def logerr(self, msg):
        """ log error messages """
        self.log.error(msg)

# need to rethink
period_timespan = {
    # pylint: disable=unnecessary-lambda
    'hour': lambda time_stamp: weeutil.weeutil.archiveHoursAgoSpan(time_stamp),
    'day': lambda time_stamp: weeutil.weeutil.archiveDaySpan(time_stamp),
    'yesterday': lambda time_stamp: weeutil.weeutil.archiveDaySpan(time_stamp, 1),
    'week': lambda time_stamp: weeutil.weeutil.archiveWeekSpan(time_stamp),
    'month': lambda time_stamp: weeutil.weeutil.archiveMonthSpan(time_stamp),
    'year': lambda time_stamp: weeutil.weeutil.archiveYearSpan(time_stamp),
    'last24hours': lambda time_stamp: TimeSpan(time_stamp, time_stamp - 86400),
    'last7days': lambda time_stamp: TimeSpan(time_stamp,
                                             time.mktime((datetime.date.fromtimestamp(time_stamp) -
                                                          datetime.timedelta(days=7)).timetuple())),
    'last31days': lambda time_stamp: TimeSpan(time_stamp,
                                              time.mktime((datetime.date.fromtimestamp(time_stamp) -
                                                           datetime.timedelta(days=31)).timetuple())),
    'last366days': lambda time_stamp: TimeSpan(time_stamp,
                                               time.mktime((datetime.date.fromtimestamp(time_stamp) -
                                                            datetime.timedelta(days=366)).timetuple()))
}
# pylint: enable=unnecessary-lambda

class AbstractPublisher(abc.ABC):
    """ Managing publishing to MQTT. """
    def __init__(self, logger, publisher, mqtt_config):
        self.logger = logger
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

        self.client = self.get_client(mqtt_config['clientid'], mqtt_config['protocol'])
        self.set_callbacks(mqtt_config['log_mqtt'])

        if mqtt_config['username'] is not None and mqtt_config['password'] is not None:
            self.client.username_pw_set(mqtt_config['username'], mqtt_config['password'])

        tls_dict = mqtt_config.get('tls')
        if tls_dict and to_bool(tls_dict.get('enable', True)):
            self._config_tls(tls_dict)

        self.lwt_dict = mqtt_config.get('lwt')
        if self.lwt_dict and to_bool(self.lwt_dict.get('enable', True)):
            self.client.will_set(topic=self.lwt_dict.get('topic', 'status'),
                                 payload=self.lwt_dict.get('offline_payload', 'offline'),
                                 qos=to_int(self.lwt_dict.get('qos', 0)),
                                 retain=to_bool(self.lwt_dict.get('retain', True)))

        self._connect()

    @classmethod
    def get_publisher(cls, logger, publisher, mqtt_config):
        ''' Factory method to get appropriate MQTTPublish for paho mqtt version. '''
        if hasattr(mqtt, 'CallbackAPIVersion'):
            protocol = mqtt_config['protocol']
            if protocol in [mqtt.MQTTv31, mqtt.MQTTv311]:
                return PublisherV2MQTT3(logger, publisher, mqtt_config)

            return PublisherV2(logger, publisher, mqtt_config)

        return PublisherV1(logger, publisher, mqtt_config)

    def _connect(self):
        try:
            self.connect(self.mqtt_config['host'], self.mqtt_config['port'], self.mqtt_config['keepalive'])
        except Exception as exception:  # want to catch all pylint: disable=broad-exception-caught
            self.logger.logerr(f"MQTT connect failed with {type(exception)} and reason {exception}.")
            self.logger.logerr(f"{traceback.format_exc()}")
        retries = 0
        # loop seems to break before connect, perhaps due to logging
        self.client.loop(timeout=0.1)
        time.sleep(1)
        while not self.connected:
            self.logger.logdbg("waiting")
            # loop seems to break before connect, perhaps due to logging
            self.client.loop(timeout=0.1)
            time.sleep(5)

            retries += 1
            if retries > self.mqtt_config['max_retries']:
                # Shut thread down, a bit of a hack
                self.publisher.running = False
                return

            try:
                self.connect(self.mqtt_config['host'], self.mqtt_config['port'], self.mqtt_config['keepalive'])
            except Exception as exception:  # want to catch all pylint: disable=broad-exception-caught
                self.logger.logerr(f"MQTT connect failed with {type(exception)} and reason {exception}.")
                self.logger.logerr(f"{traceback.format_exc()}")

    def _reconnect(self):
        self.logger.logdbg("*** Before reconnect ***")
        self.client.reconnect()
        self.logger.logdbg("*** After reconnect ***")
        retries = 0
        self.logger.logdbg("*** Before loop ***")
        self.client.loop(timeout=1.0)
        self.logger.logdbg("*** After loop ***")
        while not self.connected:
            self.logger.logdbg("waiting")
            self.client.loop(timeout=5.0)

            retries += 1
            if retries > self.mqtt_config['max_retries']:
                # Shut thread down, a bit of a hack
                self.publisher.running = False
                return

            self.client.reconnect()

        self.logger.loginf("reconnected")

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

        valid_cert_reqs = valid_cert_reqs.get(tls_dict.get('certs_required', 'required'))
        if valid_cert_reqs is None:
            raise ValueError(f"Invalid 'certs_required'., {tls_dict['certs_required']}")

        tls_version = valid_tls_versions.get(tls_dict.get('tls_version', 'tlsv12'))
        if tls_version is None:
            raise ValueError(f"Invalid 'tls_version'., {tls_dict['tls_version']}")

        self.client.tls_set(ca_certs=ca_certs,
                            certfile=tls_dict.get('certfile'),
                            keyfile=tls_dict.get('keyfile'),
                            cert_reqs=valid_cert_reqs,
                            tls_version=tls_version,
                            ciphers=tls_dict.get('ciphers'))

    def publish_message(self, time_stamp, qos, retain, topic, data):
        """ Publish the message. """
        if not self.connected:
            self._reconnect()
        mqtt_message_info = self.client.publish(topic, data, qos=qos, retain=retain)
        self.logger.logdbg(f"Publishing ({int(time.time())}): {int(time_stamp)} {mqtt_message_info.mid} {qos} {topic}")

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

class PublisherV1(AbstractPublisher):
    ''' MQTTPublish that communicates with paho mqtt v1.'''
    def __init__(self, logger, publisher, mqtt_config):
        protocol = mqtt_config['protocol']
        if protocol not in [mqtt.MQTTv31, mqtt.MQTTv311]:
            raise ValueError(f"Invalid protocol, {protocol}.")

        super().__init__(logger, publisher, mqtt_config)

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

    def connect(self, host, port, keepalive):
        self.client.connect(host, port, keepalive)

    def on_log(self, _client, _userdata, level, msg):
        self.mqtt_logger[level](f"MQTT log: {msg}")

    def on_connect(self, _client, _userdata, flags, reason_code, properties=None):
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
        if self.lwt_dict and to_bool(self.lwt_dict.get('enable', True)):
            self.client.publish(topic=self.lwt_dict.get('topic', 'status'),
                                payload=self.lwt_dict.get('online_payload', 'online'),
                                qos=to_int(self.lwt_dict.get('qos', 0)),
                                retain=to_bool(self.lwt_dict.get('retain', True)))
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
        self.logger.logdbg(f"Published  ({int(time.time())}): {time_stamp} {mid} {qos}")

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

    def connect(self, host, port, keepalive):
        self.client.connect(host=host, port=port, keepalive=keepalive, clean_start=True)

    def on_log(self, _client, _userdata, level, msg):
        self.mqtt_logger[level](f"MQTT log: {msg}")

    def on_connect(self, _client, _userdata, flags, reason_code, _properties):
        self.logger.loginf(f"Connected with result code {int(int(reason_code.value))}")
        self.logger.loginf(f"Connected flags {str(flags)}")
        if self.lwt_dict and to_bool(self.lwt_dict.get('enable', True)):
            self.client.publish(topic=self.lwt_dict.get('topic', 'status'),
                                payload=self.lwt_dict.get('online_payload', 'online'),
                                qos=to_int(self.lwt_dict.get('qos', 0)),
                                retain=to_bool(self.lwt_dict.get('retain', True)))
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
        self.logger.logdbg(f"Published  ({int(time.time())}): {time_stamp} {mid} {qos}")

class PublisherV2MQTT3(PublisherV2):
    ''' MQTTPublish that communicates with paho mqtt v2. '''
    def get_client(self, client_id, protocol):
        return mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                           protocol=protocol,
                           client_id=client_id,
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

        self.logger.logdbg(f" native id in 'main' init {threading.get_native_id()}")

        service_dict = config_dict.get('MQTTPublish', {})

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

        self.topics_loop, self.topics_archive = self.configure_topics(service_dict)

        self.mqtt_config = {}
        self.mqtt_config['keepalive'] = to_int(service_dict.get('keepalive', 60))

        self.mqtt_config['max_retries'] = to_int(service_dict.get('max_retries', 5))
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

        # todo - make configurable
        self.kill_weewx = []
        self.max_thread_restarts = 2
        self.thread_restarts = 0

        # todo, tie this into the topic bindings somehow...
        # But note, this is also the default setting for topics
        binding = weeutil.weeutil.option_as_list(service_dict.get('binding', ['archive', 'loop']))

        self.data_queue = Queue.Queue()

        if 'loop' in binding:
            self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)

        if 'archive' in binding:
            self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)

        self._thread = PublishWeeWXThread(self.logger, self.mqtt_config, self.topics_loop, self.topics_archive, self.data_queue)
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

        # self.logger.logdbg("Configured fields: %s" % fields)
        return fields

    def configure_topics(self, service_dict):
        """ Configure the topics. """
        # ToDo: cleanup 'topic_dic1' once tests are in place
        topic_dict1 = service_dict.get('topics', None)

        if topic_dict1 is None:
            raise ValueError("[[topics]] is required.")

        default_qos = to_int(service_dict.get('qos', 0))
        default_retain = to_bool(service_dict.get('retain', False))
        default_type = service_dict.get('type', 'json')
        default_binding = weeutil.weeutil.option_as_list(service_dict.get('binding', ['archive', 'loop']))

        default_append_label = service_dict.get('append_unit_label', True)
        default_conversion_type = service_dict.get('conversion_type', 'string')
        default_format_string = service_dict.get('format', '%s')

        topics_loop = {}
        topics_archive = {}
        for topic in topic_dict1.sections:
            topic_dict = topic_dict1.get(topic, {})
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
            format_string = topic_dict.get('format', default_format_string)
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
                for aggregate in aggregates:
                    if to_bool(aggregates[aggregate].get('enable', True)) and aggregates[aggregate]['period'] not in period_timespan:
                        raise ValueError(f"Invalid 'period', {aggregates[aggregate]['period']}")
                weeutil.config.merge_config(aggregates, self.configure_fields(aggregates,
                                                                              ignore,
                                                                              publish_none_value,
                                                                              append_unit_label,
                                                                              conversion_type,
                                                                              format_string))

            # self.logger.logdbg("Configured aggregates: %s" % aggregates)

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
                topics_loop[topic]['format'] = format_string
                topics_loop[topic]['fields'] = dict(fields)
                topics_loop[topic]['aggregates'] = dict(aggregates)

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
                topics_archive[topic]['format'] = format_string
                topics_archive[topic]['fields'] = dict(fields)
                topics_archive[topic]['aggregates'] = dict(aggregates)

        self.logger.logdbg(f"Loop topics: {topics_loop}")
        self.logger.logdbg(f"Archive topics: {topics_archive}")
        return topics_loop, topics_archive

    def thread_start(self):
        """Start the publishing thread."""
        self.logger.loginf("starting thread")
        self._thread.start()
        # ToDo - configure how long to wait for thread to start
        self.thread_start_wait = 5.0
        self.logger.loginf("joining thread")
        # self._thread.join(self.thread_start_wait)
        self.logger.loginf("joined thread")

        if not self._thread.is_alive():
            self.logger.loginf("oh no")
            raise weewx.WakeupError("Unable to start MQTT publishing thread.")

        self.logger.loginf("started thread")

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
                    PublishWeeWXThread(self.logger, self.mqtt_config, self.topics_loop, self.topics_archive, self.data_queue)
                self.thread_start()

                self.data_queue.put({'time_stamp': data['dateTime'], 'type': data_type, 'data': data})
                self._thread.threading_event.set()
            elif 'threadEnded' in self.kill_weewx:
                raise weewx.StopNow("MQTT publishing thread has stopped.")
        else:
            self.data_queue.put({'time_stamp': data['dateTime'], 'type': data_type, 'data': data})
            self._thread.threading_event.set()

    def shutDown(self):
        """Run when an engine shutdown is requested."""
        self.logger.loginf("SHUTDOWN - initiated")
        if self._thread:
            self.logger.loginf("SHUTDOWN - thread initiated")
            self._thread.running = False
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

    def __init__(self, logger, mqtt_config, topics_loop, topics_archive, data_queue):
        threading.Thread.__init__(self)
        self.logger = logger

        self.logger.logdbg(f" native id in init {threading.get_native_id()}")

        self.publisher = None
        self.running = False

        self.db_manager = None

        self.mqtt_config = mqtt_config
        self.topics_loop = topics_loop
        self.topics_archive = topics_archive

        self.data_queue = data_queue
        self.threading_event = threading.Event()

    def update_record(self, topic_dict, record):
        """ Update the record. """
        final_record = {}
        updated_record = weewx.units.to_std_system(record, topic_dict['unit_system'])

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

        for aggregate_observation in topic_dict['aggregates']:
            # self.logger.logdbg(topic_dict['aggregates'][aggregate_observation])
            if not to_bool(topic_dict['aggregates'][aggregate_observation].get('enable', True)):
                continue

            time_span = period_timespan[topic_dict['aggregates'][aggregate_observation]['period']](record['dateTime'])

            try:
                aggregate_value_tuple = \
                    weewx.xtypes.get_aggregate(topic_dict['aggregates'][aggregate_observation]['observation'],
                                               time_span, topic_dict['aggregates'][aggregate_observation]['aggregation'],
                                               self.db_manager)
                aggregate_value = weewx.units.convertStd(aggregate_value_tuple, record['usUnits'])[0]
                # ToDo: only do once?
                weewx.units.obs_group_dict[aggregate_observation] = aggregate_value_tuple[2]

                (name, value) = self.update_field(topic_dict, topic_dict['aggregates'][aggregate_observation],
                                                  aggregate_observation,
                                                  aggregate_value,
                                                  updated_record['usUnits'])

                # ToDo: check if observation already in record
                final_record[name] = value

            except (weewx.CannotCalculate, weewx.UnknownAggregation, weewx.UnknownType) as exception:
                self.logger.logerr(f"Aggregation failed: {exception}")
                self.logger.logerr(traceback.format_exc())

        return final_record

    @staticmethod
    def update_field(topic_dict, fieldinfo, field, value, unit_system):
        """ Update field. """
        name = fieldinfo.get('name', field)
        append_unit_label = fieldinfo.get('append_unit_label', topic_dict.get('append_unit_label'))
        if append_unit_label:
            (unit_type, _) = weewx.units.getStandardUnitType(unit_system, name)
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
        format_string = fieldinfo.get('format', topic_dict.get('format'))
        if conversion_type == 'integer':
            formatted_value = to_int(converted_value)
        else:
            formatted_value = format_string % converted_value
            if conversion_type == 'float':
                formatted_value = to_float(formatted_value)

        return name, formatted_value

    def publish_row(self, time_stamp, data, topics):
        """ Publish the data. """
        record = data

        for topic in topics:
            if topics[topic]['type'] == 'json':
                updated_record = self.update_record(topics[topic], record)
                self.publisher.publish_message(time_stamp,
                                               topics[topic]['qos'],
                                               topics[topic]['retain'],
                                               topic,
                                               json.dumps(updated_record))
            if topics[topic]['type'] == 'keyword':
                updated_record = self.update_record(topics[topic], record)
                data_keyword = ', '.join(f"{key}={val}" for (key, val) in updated_record.items())
                self.publisher.publish_message(time_stamp,
                                               topics[topic]['qos'],
                                               topics[topic]['retain'],
                                               topic,
                                               data_keyword)
            if topics[topic]['type'] == 'individual':
                updated_record = self.update_record(topics[topic], record)
                for key, value in updated_record.items():
                    self.publisher.publish_message(time_stamp,
                                                   topics[topic]['qos'],
                                                   topics[topic]['retain'],
                                                   topic + '/' + key,
                                                   value)

    def run(self):
        self.running = True
        self.logger.logdbg(f"{self.name} {threading.get_ident()}")
        self.logger.logdbg(f" native id in run {threading.get_native_id()}")

        # need to instantiate inside thread
        self.publisher = AbstractPublisher.get_publisher(self.logger, self, self.mqtt_config)

        while self.running:
            try:
                data2 = self.data_queue.get_nowait()
                time_stamp = data2['time_stamp']
                data_type = data2['type']
                data = data2['data']
                if data_type == 'loop':
                    self.publish_row(time_stamp, data, self.topics_loop)
                elif data_type == 'archive':
                    self.publish_row(time_stamp, data, self.topics_archive)
                else:
                    self.logger.logerr(f"Unknown data type, {data_type}")
            except Queue.Empty:
                # todo this causes another connection, seems to cause no harm
                # does cause a socket error/disconnect message on the server
                self.publisher.client.loop(timeout=0.1)
                # ToDo - investigate my 'sleep' implementation
                self.threading_event.wait(self.mqtt_config['keepalive'] / 4)
                self.threading_event.clear()

        self.logger.loginf("exited loop")
        self.logger.loginf("thread shutdown")

if __name__ == "__main__":
    def main():
        """ Run it. """
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

        config_dict = {
            'debug': 1,
            'MQTTPublish': {
                'topics': {
                    'test/loop': {
                        'binding': 'loop',
                        'type': 'json'
                    }
                }
            },
            'Logging': {
                'root': {
                    'handlers': ['syslog', 'console']
                },
                'loggers': {
                    'user.mqttpublish': {
                        'level': 'DEBUG'
                    }
                }
            }
        }
        config = configobj.ConfigObj(config_dict)

        setup_logging(True, config_dict)
        mqtt_publish = MQTTPublish(engine, config)

        with open('tmp/message.json', encoding='UTF-8') as file_object:
            packets = json.load(file_object)

        for packet in packets:
            new_loop_packet_event = weewx.Event(weewx.NEW_LOOP_PACKET, packet=packet)
            engine.dispatchEvent(new_loop_packet_event)

        # Attempt to wait for all packets to be processed
        # ToDo: Add a max number of time the sleep/loop runs
        while mqtt_publish._thread.threading_event.is_set():  # pylint: disable=protected-access
            print("sleepting")
            time.sleep(1)

        mqtt_publish.shutDown()

    main()

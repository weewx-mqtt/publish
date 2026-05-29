#
#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

""" Plugin to perform Home Assistant MQTT Discovery """

from io import StringIO
import json

import configobj

# homeassistant/device/ea334450945afc/config
CONFIG_STR = """
[devices]
    [[ea334450945afc]]
        state_topic = weather/loop
        qos = 2
        [[[device]]]
            identifiers =
            name = Kitchen
            manufacturer = Bla electronics
            model = xya
            sw_version = 1.0
            serial_number = ea334450945afc
            hw_version = 1.0rev2
        [[[origin]]]
            name = bla2mqtt
            sw_version = 2.1
            support_url = https://bla2mqtt.example.com/support
        [[[components]]]
            #[[[[outTemp]]]]
            #    platform = sensor
            #    #device_class = temperature
            #    #unit_of_measurement = °F
            #    value_template = {{ value_json.outTemp | default(this.state)}}
            #    unique_id = outTemp
            #[[[[outHumidity]]]]
            #    platform = sensor
            #    #device_class = humidity
            #    #unit_of_measurement = %
            #    value_template = {{ value_json.outHumidity | default(this.state) }}
            #    unique_id = outHumidity
        [[[availability]]]
            topic = status
            payload_available = online
            payload_not_available = offline
"""

class MQTTHomeAssistantConfig:
    """ Publish Home Assistant sensor configuration data. """
    def __init__(self, logger, name):
        self.logger = logger
        self.name = name

        self.config = configobj.ConfigObj(StringIO(CONFIG_STR))
        self.state_topics = {}
        for device_id in self.config['devices']:
            device_config = self.config['devices'][device_id]
            device_config['device']['identifiers'] = device_id
            self.state_topics[device_config['state_topic']] = {}

        # ToDo: Figure out how to configure
        self.birth_topic = "status"
        self.lwt_topic = "status"
        self.qos = 1

    def get_callbacks(self):
        """ The callbacks. """
        return [
            {
                'on_weewx_data': {
                    'timing': 'immediate',
                    'callback': self.on_weewx_data
                }
            },
            {
                'on_mqtt_connect': {
                    'timing': 'immediate',
                    'callback': self.on_mqtt_connect
                }
            },
            {
                'on_mqtt_message': {
                    'timing': 'immediate',
                    'callback': self.on_mqtt_message
                },
                'publish_record': {
                    'timing': 'immediate',
                    'callback': self.publish_record
                },
            },
        ]

    def on_weewx_data(self, data):
        """ Handle WeeWX archive and loop data. """
        self.logger.logdbg(data)

    def on_mqtt_message(self, _client, userdata, msg):
        """ Handle the MQTT on_message callback. """
        self.logger.logdbg(f"Received: {userdata} {msg}")
        if msg.topic == self.birth_topic and msg.payload == b"online":
            self.logger.loginf("ToDo: resend the configuration data to HA")
        elif msg.topic == self.lwt_topic and msg.payload == b"offline":
            self.logger.loginf(f"Received LWT {msg.payload} on topic: {msg.topic}.")
        else:
            self.logger.logerr(f"Received invalid {msg.payload} on topic: {msg.topic}.")

    def on_mqtt_connect(self, mqtt_client, _userdata, _flags, _reason_code, _properties):
        """ Handle the MQTT on_connect callback. """
        (result, mid) = mqtt_client.subscribe(self.birth_topic, self.qos)
        self.logger.loginf(f"Subscribing to topic {self.birth_topic} "
                           f"returned mid {int(mid)} "
                           f"and result {int(result)}.")

        (result, mid) = mqtt_client.subscribe(self.lwt_topic, self.qos)
        self.logger.loginf(f"Subscribing to topic {self.lwt_topic} "
                           f"returned mid {int(mid)} "
                           f"and result {int(result)}.")

    def publish_record(self, mqtt_client, topic, data, _qos, _retain):
        """ Run code when MQTT message is published. """
        # ToDo: proof of concept code
        self.logger.logdbg("start")
        for device_id in self.config['devices']:
            new_sensor = False
            if topic in self.state_topics:
                for field in data:
                    if field not in self.state_topics[topic]:
                        new_sensor = True
                        self.state_topics[topic][field] = {}
                        value_template = '{{ value_json.' + field + ' | default(this.state) }}'
                        self.config['devices'][device_id]['components'][field] = {
                            'platform': 'sensor',
                            'value_template': value_template,
                            'unique_id': field,
                            'name': field,
                        }

                if new_sensor:
                    payload = json.dumps(self.config['devices'][device_id])
                    topic = 'homeassistant/device/ea334450945afc/config'
                    mqtt_message_info = mqtt_client.publish(topic, payload, qos=0, retain=False)
                    self.logger.logdbg(f"publishing: {mqtt_message_info.mid} {topic}")

        self.logger.logdbg("done")

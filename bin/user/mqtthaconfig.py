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
        state_topic = weather/archive
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
            [[[[some_unique_component_id1]]]]
                platform = sensor
                device_class = temperature
                unit_of_measurement = °F
                value_template = {{ value_json.outTemp}}
                unique_id = temp01ae_t
            [[[[some_unique_id2]]]]
                platform = sensor
                device_class = humidity
                unit_of_measurement = %
                value_template = {{ value_json.outHumidity}}
                unique_id = temp01ae_hs
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

        # ToDo: Figure out how to configure
        self.birth_topic = "homeassistant/status"
        self.lwt_topic = "homeassistant/status"
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
                'publish_message': {
                    'timing': 'immediate',
                    'callback': self.publish_message
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

    def publish_message(self, mqtt_client, _topic, _data, _qos, _retain):
        """ Run code when MQTT message is published. """
        # ToDo: proof of concept code
        config = configobj.ConfigObj(StringIO(CONFIG_STR))
        # print(config['devices'])
        for device_id in config['devices']:
            print(device_id)
            device_config = config['devices'][device_id]
            device_config['device']['identifiers'] = device_id
            print(device_config)
            payload = json.dumps(device_config)
            print(payload)

            topic = 'homeassistant/device/ea334450945afc/config'
            qos = 0
            retain = False

            #mqtt_message_info = mqtt_client.publish(topic, payload, qos=qos, retain=retain)
            #self.logger.logdbg(f"publishing: {mqtt_message_info.mid} {qos} {topic}")

        self.logger.loginf("done")

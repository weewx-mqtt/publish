#
#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

class MQTTHomeAssistantConfig:
    """ Publish Home Assistant sensor configuration data. """
    def __init__(self, logger, name):
        self.logger = logger
        self.name = name

        # ToDo: Figure out how to configure
        self.discovery_topic = "homeassistant/status"
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
                }
            },
        ]

    def on_weewx_data(self, data):
        """ Handle WeeWX archive and loop data. """
        self.logger.logdbg(data)

    def on_mqtt_message(self, _client, userdata, msg):
        """ Handle the MQTT on_message callback. """
        self.logger.logdbg(f"Received: {userdata} {msg}")

    def on_mqtt_connect(self, mqtt_client, _userdata, _flags, _reason_code, _properties):
        """ Handle the MQTT on_connect callback. """
        (result, mid) = mqtt_client.subscribe(self.discovery_topic, self.qos)
        self.logger.loginf(f"Subscribing to topic {self.discovery_topic} "
                           f"returned mid {int(mid)} "
                           f"and result {int(result)}.")

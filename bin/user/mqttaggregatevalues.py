#
#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

""" Plugin to calculate aggregate values. """

from weeutil.weeutil import to_bool

class MQTTAggregateValues:
    """ Calculate aggregate values. """
    def __init__(self, logger, name, plugin_dict, weewx_defaults):
        self.logger = logger
        self.name = name
        self.weewx_defaults = weewx_defaults
        self.enabled = to_bool(plugin_dict.get('enable', True))

    def get_callbacks(self):
        """ The callbacks. """
        if not self.enabled:
            return []

        return [
            {
                'update_record': {
                    'timing': 'immediate',
                    'callback': self.update_record
                },
            },
        ]

    def update_record(self, _mqtt_client, topic, data, _qos, _retain):
        """ Run code when MQTT record is updated. """

        print(topic)
        print(data)

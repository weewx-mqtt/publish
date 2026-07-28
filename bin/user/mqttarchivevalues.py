#
#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

""" Plugin to copy archive values into data being published. """

# ToDo: Do I need to configure fields?

import weeutil
from weeutil.weeutil import to_bool
import weewx

class MQTTArchiveValues:
    """ Calculate aggregate values. """
    def __init__(self, logger, name, plugin_dict, _mqtt_dict, _topics, _weewx_dict):
        self.logger = logger
        self.name = name
        self.plugin_dict = weeutil.config.deep_copy(plugin_dict)
        self.enabled = to_bool(self.plugin_dict.get('enable', True))

        if not self.enabled:
            self.logger.loginf(f"Plugin {self.name} is not enabled.")
            return

        self.archive_data = {}

    def get_callbacks(self):
        """ The callbacks. """
        if not self.enabled:
            return []

        return [
            {
                'on_weewx_data': {
                    'timing': 'immediate',
                    'callback': self.on_weewx_data
                },
                'update_record': {
                    'timing': 'delay',
                    'callback': self.update_record
                },
            },
        ]

    def on_weewx_data(self, data):
        """ Run code when MQTT record is updated. """
        if data['type'] == 'archive':
            self.archive_data = data['data']
            print(self.archive_data)

    def update_record(self, _mqtt_client, topic, data, units, _qos, _retain):
        """ Run code when MQTT record is updated. """
        if topic in self.plugin_dict['topics']:
            for fieldname in self.archive_data:
                if fieldname not in data and self.archive_data[fieldname] is not None:
                    (to_unit, _) = weewx.units.getStandardUnitType(units, fieldname)
                    (from_unit, from_group) = weewx.units.getStandardUnitType(self.archive_data['usUnits'], fieldname)
                    from_tuple = (self.archive_data[fieldname], from_unit, from_group)
                    converted_value = weewx.units.convert(from_tuple, to_unit)[0]
                    data[fieldname] = converted_value

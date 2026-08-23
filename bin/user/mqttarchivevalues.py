#
#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

""" Plugin to copy archive values into data being published. """

# ###################################################################################################################################
#
# WeeWX does not 'publish' archive records in real time. There is a built-in (configurable) delay.
# But it does keep 'publishing' loop packets in real time.
# This means that the loop packets 'published' during this delay will have the archive record data from the previous archive period.
# There is nothing MQTTArchiveValues can do about that
#
# ###################################################################################################################################

import weeutil
from weeutil.weeutil import to_bool, to_list
import weewx

class MQTTArchiveValues:
    """ Calculate aggregate values. """
    def __init__(self, logger_queue, name, plugin_dict, _mqtt_dict, _topics, _weewx_dict):
        self.logger_queue = logger_queue
        self.name = name
        self.plugin_dict = weeutil.config.deep_copy(plugin_dict)
        self.enabled = to_bool(self.plugin_dict.get('enable', True))

        if not self.enabled:
            self.logger_queue.put({'log_type': 'INFO',
                                   'log_message': f"Plugin {self.name} is not enabled."})
            return

        # ToDo: check that these are mutually exclusive
        self.ignore_fields = to_list(self.plugin_dict.get('ignore_fields', []))
        self.add_fields = to_list(self.plugin_dict.get('add_fields', []))

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
                if self.add_fields and fieldname not in self.add_fields:
                    continue
                if fieldname in self.ignore_fields:
                    continue

                if fieldname not in data and self.archive_data[fieldname] is not None:
                    (to_unit, _) = weewx.units.getStandardUnitType(units, fieldname)
                    (from_unit, from_group) = weewx.units.getStandardUnitType(self.archive_data['usUnits'], fieldname)
                    from_tuple = (self.archive_data[fieldname], from_unit, from_group)
                    converted_value = weewx.units.convert(from_tuple, to_unit)[0]
                    data[fieldname] = converted_value

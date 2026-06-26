#
#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

""" Plugin to perform Home Assistant MQTT Discovery """

from io import StringIO
import json

import configobj

import weewx.units
import weeutil

from weeutil.weeutil import to_bool, to_int, to_list

# hDevice class and unit of measure: https://developers.home-assistant.io/docs/core/entity/sensor/#available-device-classes
DEFAULT_COMPONENT_DATA = """
        [dateTime]
            device_class =  timestamp
            value_template = '{{ as_datetime(value_json.dateTime | default(this.value)) }}'
            icon = mdi:clock
        [usUnits]
            device_class =  enum
        [interval]
        [altimeter]
            device_class =  atmospheric_pressure
        [appTemp]
            device_class =  temperature
        [appTemp1]
            device_class =  temperature
        [barometer]
            device_class =  atmospheric_pressure
        [batteryStatus1]
            device_class =  battery
        [batteryStatus2]
            device_class =  battery
        [batteryStatus3]
            device_class =  battery
        [batteryStatus4]
            device_class =  battery
        [batteryStatus5]
            device_class =  battery
        [batteryStatus6]
            device_class =  battery
        [batteryStatus7]
            device_class =  battery
        [batteryStatus8]
            device_class =  battery
        [cloudbase]
            device_class =  distance
        [co]
            device_class =  carbon_monoxide
        [co2]
            device_class =  carbon_dioxide
        [consBatteryVoltage]
            device_class =  voltage
        [dewpoint]
            device_class =  temperature
        [dewpoint1]
            device_class =  temperature
        [ET]
        [extraHumid1]
            device_class =  humidity
        [extraHumid2]
            device_class =  humidity
        [extraHumid3]
            device_class =  humidity
        [extraHumid4]
            device_class =  humidity
        [extraHumid5]
            device_class =  humidity
        [extraHumid6]
            device_class =  humidity
        [extraHumid7]
            device_class =  humidity
        [extraHumid8]
            device_class =  humidity
        [extraTemp1]
            device_class =  temperature
        [extraTemp2]
            device_class =  temperature
        [extraTemp3]
            device_class =  temperature
        [extraTemp4]
            device_class =  temperature
        [extraTemp5]
            device_class =  temperature
        [extraTemp6]
            device_class =  temperature
        [extraTemp7]
            device_class =  temperature
        [extraTemp8]
            device_class =  temperature
        [forecast]
        [hail]
            device_class =  precipitation
        [hailBatteryStatus]
            device_class =  battery
        [hailRate]
        [heatindex]
            device_class =  temperature
        [heatindex1]
            device_class =  temperature
        [heatingTemp]
            device_class =  temperature
        [heatingVoltage]
            device_class =  voltage
        [humidex]
        [humidex1]
        [illuminance]
            device_class =  illuminance
        [inDewpoint]
            device_class =  temperature
        [inHumidity]
            device_class =  humidity
        [inTemp]
            device_class =  temperature
        [inTempBatteryStatus]
            device_class =  battery
        [leafTemp1]
            device_class =  temperature
        [leafTemp2]
            device_class =  temperature
        [leafWet1]
            device_class =  moisture
        [leafWet2]
            device_class =  moisture
        [lightning_distance]
            device_class =  distance
        [lightning_disturber_count]
        [lightning_energy]
        [lightning_noise_count]
        [lightning_strike_count]
        [luminosity]
        [maxSolarRad]
            device_class =  irradiance
        [nh3]
        [no2]
            device_class =  nitogen_dioxide
        [noise]
            device_class =  sound_pressure
        [o3]
            device_class =  ozone
        [outHumidity]
            device_class =  humidity
        [outTemp]
            device_class =  temperature
            state_class = measurement
        [outTempBatteryStatus]
            device_class =  battery
        [pb]
        [pm10_0]
            device_class =  pm10
        [pm1_0]
            device_class =  pm1
        [pm2_5]
            device_class =  pm25
        [pressure]
            device_class =  atmospheric_pressure
        [radiation]
            device_class =  irradiance
        [rain]
            device_class =  precipitation
            state_class = total
        [rainBatteryStatus]
            device_class =  battery
        [rainRate]
            device_class =  precipitation_intensity
        [referenceVoltage]
            device_class =  voltage
        [rxCheckPercent]
        [signal1]
        [signal2]
        [signal3]
        [signal4]
        [signal5]
        [signal6]
        [signal7]
        [signal8]
        [snow]
            device_class =  precipitation
        [snowBatteryStatus]
            device_class =  battery
        [snowDepth]
            device_class =  distance
        [snowMoisture]
            device_class =  moisture
        [snowRate]
            device_class =  precipitation_intensity
        [so2]
            device_class =  sulphur_dioxide
        [soilMoist1]
            device_class =  moisture
        [soilMoist2]
            device_class =  moisture
        [soilMoist3]
            device_class =  moisture
        [soilMoist4]
            device_class =  moisture
        [soilTemp1]
            device_class =  temperature
        [soilTemp2]
            device_class =  temperature
        [soilTemp3]
            device_class =  temperature
        [soilTemp4]
            device_class =  temperature
        [supplyVoltage]
            device_class =  voltage
        [txBatteryStatus]
            device_class =  battery
        [UV]
        [uvBatteryStatus]
            device_class =  battery
        [windBatteryStatus]
            device_class =  battery
        [windchill]
            device_class =  temperature
        [windDir]
            device_class =  wind_direction
            state_class =  measurement_angle
        [windGust]
            device_class =  wind_speed
        [windGustDir]
            device_class = wind_direction
            state_class = measurement_angle
        [windrun]
        [windSpeed]
            device_class =  wind_speed
"""
DEFAULT_UNITS = """
        cm = cm
        degree_C = °C
        degree_F = °F
        degree_K = K
        degree_compass = °
        foot = ft
        gallon = gal
        hPa = hPa
        hour = h
        inHg = inHg
        inch = in
        kPa = kPa
        kilowatt = kW
        kilowatt_hour = kWh
        km_per_hour = km/h
        knot = kn
        liter = L
        lux = lx
        mbar = mbar
        meter = m
        meter_per_second = m/s
        microgram_per_meter_cubed = μg/m³
        mile_per_hour = mph
        minute = min
        mm = mm
        mmHg = mmHg
        mm_per_hour = mm/h
        percent = %
        percent_battery = %
        second = s
        volt = V
        watt = W
        watt_hour = Wh
        watt_per_meter_squared = W/m²

"""
class MQTTHomeAssistantConfig:
    """ Publish Home Assistant MQTT devicde configuration data. """
    def __init__(self, logger, name, plugin_dict, weewx_dict):
        self.logger = logger
        self.name = name
        self.weewx_defaults = weewx_dict.get('defaults', {})
        self.enabled = to_bool(plugin_dict.get('enable', True))

        if not self.enabled:
            self.logger.loginf(f"Plugin {self.name} is not enabled.")
            return

        if 'devices' not in plugin_dict or len(plugin_dict['devices'].sections) == 0:
            raise ValueError("At least one device-id must be configured.")

        self.defaults = {}
        self.defaults['component_data'] = {}
        self.defaults['units'] = configobj.ConfigObj(StringIO(DEFAULT_UNITS))

        self.state_topics = {}
        self.qos = to_int(plugin_dict.get('qos', 0))
        self.birth_topic = plugin_dict.get('birth_topic', 'homeassistant/status')
        self.lwt_topic = plugin_dict.get('lqt_topic', 'homeassistant/status')
        self.mqtt_config = {}
        self.configuration = configobj.ConfigObj({})
        self.configuration['devices'] = {}

        for device_id in plugin_dict['devices']:
            self.defaults['component_data'][device_id] = configobj.ConfigObj(StringIO(DEFAULT_COMPONENT_DATA))
            # ToDo: Remove? Backwards compatibility of old location
            weeutil.config.merge_config(self.defaults['component_data'][device_id], plugin_dict.get('component_data', {}))
            # Now, get the correct location and override any other data
            weeutil.config.merge_config(self.defaults['component_data'][device_id],
                                        plugin_dict['devices'][device_id].get('component_data', {}))
            self.state_topics[device_id] = {}
            self.configuration['devices'][device_id] = {}
            device_config = plugin_dict['devices'][device_id]

            device_data = {}
            device_data['availability_topic'] = 'status'
            device_data['components'] = {}

            device_data['origin'] = weeutil.config.deep_copy(device_config.get('origin', configobj.ConfigObj({})))
            if 'name' not in device_data['origin']:
                device_data['origin']['name'] = 'WeeWX'

            device_data['device'] = weeutil.config.deep_copy(device_config.get('device', configobj.ConfigObj({})))
            device_data['device']['identifiers'] = device_id
            if 'name' not in device_data['device']:
                device_data['device']['name'] = device_id

            self.configuration['devices'][device_id] = device_data

            if 'state_topic' in device_config:
                raise ValueError("'state_topic' has been removed.")
            if 'topics' not in device_config:
                raise ValueError("'topics' is required.")
            if len(device_config['topics'].sections) == 0:
                raise ValueError("one 'topic' is required.")

            self.state_topics[device_id] = {}
            for state_topic in device_config['topics']:
                self.state_topics[device_id][state_topic] = {}
                self.state_topics[device_id][state_topic]['type'] = device_config['topics'][state_topic].get('type', 'json')

            self.mqtt_config[device_id] = {}
            self.mqtt_config[device_id]['ignore_none_value'] = to_bool(device_config.get('ignore_none_value', True))
            self.mqtt_config[device_id]['ignore_fields'] = to_list(device_config.get('ignore_fields', []))
            self.mqtt_config[device_id]['qos'] = device_config.get('qos', 0)
            self.mqtt_config[device_id]['retain'] = to_bool(device_config.get('retain', False))

    def get_callbacks(self):
        """ The callbacks. """
        if not self.enabled:
            return []

        return [
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
                'update_record': {
                    'timing': 'delay',
                    'callback': self.update_record
                },
            },
        ]

    def on_mqtt_message(self, client, userdata, msg):
        """ Handle the MQTT on_message callback. """
        self.logger.logdbg(f"Received: {userdata} {msg}")
        if msg.topic == self.birth_topic and msg.payload == b"online":
            for device_id in self.configuration['devices']:
                self.publish_record(client, device_id)
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

    def update_record(self, mqtt_client, topic, data, _qos, _retain):
        """ Run code when MQTT message is published. """
        for device_id in self.configuration['devices']:
            new_component = False
            if topic in self.state_topics[device_id]:
                for field in data:
                    if 'ignore_fields' in self.mqtt_config[device_id] and field in self.mqtt_config[device_id]['ignore_fields']:
                        continue
                    if data[field] is None and self.mqtt_config[device_id]['ignore_none_value']:
                        continue
                    if field not in self.configuration['devices'][device_id]['components']:
                        new_component = True

                        if self.state_topics[device_id][topic]['type'] == 'individual':
                            state_topic = f'{topic}/{field}'
                            value_template = '{{ value }}'
                        else:
                            state_topic = topic
                            value_template = '{{ value_json.' + field + ' | default(this.state) }}'

                        self.configuration['devices'][device_id]['components'][field] = {
                            'state_topic': state_topic,
                            'platform': 'sensor',
                            'value_template': value_template,
                            'unique_id': f'{device_id}_{field}',
                            'name': self.weewx_defaults['Labels']['Generic'].get(field, field),
                            # 'availability': '"{{ True if has_value(this.state) else False }}"',
                        }
                        (unit, _) = weewx.units.getStandardUnitType(data['usUnits'], field)
                        unit_of_measurement = None
                        if unit:
                            unit_of_measurement = self.defaults['units'].get(unit)
                            if unit_of_measurement:
                                self.configuration['devices'][device_id]['components'][field]['unit_of_measurement'] = \
                                    unit_of_measurement
                        device_class = self.defaults['component_data'][device_id].get(field, {}).get('device_class')
                        if device_class and unit_of_measurement is not None:
                            self.configuration['devices'][device_id]['components'][field]['device_class'] = device_class
                        state_class = self.defaults['component_data'][device_id].get(field, {}).get('state_class')
                        if state_class:
                            self.configuration['devices'][device_id]['components'][field]['state_class'] = state_class

                        weeutil.config.merge_config(self.configuration['devices'][device_id]['components'][field],
                                                    self.defaults['component_data'][device_id].get(field, {}))
                        self.logger.loginf((f"New device configuration {field}: "
                                            f"{self.configuration['devices'][device_id]['components'][field]}"))

                if new_component:
                    self.publish_record(mqtt_client, device_id)

    def publish_record(self, mqtt_client, device_id):
        """ Publish the HA device discovery configuration data. """
        payload = json.dumps(self.configuration['devices'][device_id])
        topic = f'homeassistant/device/{device_id}/config'
        mqtt_message_info = mqtt_client.publish(topic,
                                                payload,
                                                qos=self.mqtt_config[device_id]['qos'],
                                                retain=self.mqtt_config[device_id]['retain'])
        self.logger.logdbg(f"publishing: {mqtt_message_info.mid} {topic} {payload}")

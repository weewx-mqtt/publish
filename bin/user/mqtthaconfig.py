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

# homeassistant/device/ea334450945afc/config
CONFIG_STR = """
    [device_data]
        [[dateTime]]
            # class = timestamp
        [[usUnits]]
            class = enum
        [[interval]]
        [[altimeter]]
            class = atmospheric_pressure
        [[appTemp]]
            class = temperature
        [[appTemp1]]
            class = temperature
        [[barometer]]
            class = atmospheric_pressure
        [[batteryStatus1]]
            class = battery
        [[batteryStatus2]]
            class = battery
        [[batteryStatus3]]
            class = battery
        [[batteryStatus4]]
            class = battery
        [[batteryStatus5]]
            class = battery
        [[batteryStatus6]]
            class = battery
        [[batteryStatus7]]
            class = battery
        [[batteryStatus8]]
            class = battery
        [[cloudbase]]
            class = distance
        [[co]]
            class = carbon_monoxide
        [[co2]]
            class = carbon_dioxide
        [[consBatteryVoltage]]
            class = voltage
        [[dewpoint]]
            class = temperature
        [[dewpoint1]]
            class = temperature
        [[ET]]
        [[extraHumid1]]
            class = humidity
        [[extraHumid2]]
            class = humidity
        [[extraHumid3]]
            class = humidity
        [[extraHumid4]]
            class = humidity
        [[extraHumid5]]
            class = humidity
        [[extraHumid6]]
            class = humidity
        [[extraHumid7]]
            class = humidity
        [[extraHumid8]]
            class = humidity
        [[extraTemp1]]
            class = temperature
        [[extraTemp2]]
            class = temperature
        [[extraTemp3]]
            class = temperature
        [[extraTemp4]]
            class = temperature
        [[extraTemp5]]
            class = temperature
        [[extraTemp6]]
            class = temperature
        [[extraTemp7]]
            class = temperature
        [[extraTemp8]]
            class = temperature
        [[forecast]]
        [[hail]]
            class = precipitation
        [[hailBatteryStatus]]
            class = battery
        [[hailRate]]
        [[heatindex]]
            class = temperature
        [[heatindex1]]
            class = temperature
        [[heatingTemp]]
            class = temperature
        [[heatingVoltage]]
            class = voltage
        [[humidex]]
        [[humidex1]]
        [[illuminance]]
            class = illuminance
        [[inDewpoint]]
            class = temperature
        [[inHumidity]]
            class = humidity
        [[inTemp]]
            class = temperature
        [[inTempBatteryStatus]]
            class = battery
        [[leafTemp1]]
            class = temperature
        [[leafTemp2]]
            class = temperature
        [[leafWet1]]
            class = moisture
        [[leafWet2]]
            class = moisture
        [[lightning_distance]]
            class = distance
        [[lightning_disturber_count]]
        [[lightning_energy]]
        [[lightning_noise_count]]
        [[lightning_strike_count]]
        [[luminosity]]
        [[maxSolarRad]]
            class = irradiance
        [[nh3]]
        [[no2]]
            class = nitogen_dioxide
        [[noise]]
            class = sound_pressure
        [[o3]]
            class = ozone
        [[outHumidity]]
            class = humidity
        [[outTemp]]
            class = temperature
        [[outTempBatteryStatus]]
            class = battery
        [[pb]]
        [[pm10_0]]
            class = pm10
        [[pm1_0]]
            class = pm1
        [[pm2_5]]
            class = pm25
        [[pressure]]
            class = atmospheric_pressure
        [[radiation]]
            class = irradiance
        [[rain]]
            class = precipitation
        [[rainBatteryStatus]]
            class = battery
        [[rainRate]]
            class = precipitation_intensity
        [[referenceVoltage]]
            class = voltage
        [[rxCheckPercent]]
        [[signal1]]
        [[signal2]]
        [[signal3]]
        [[signal4]]
        [[signal5]]
        [[signal6]]
        [[signal7]]
        [[signal8]]
        [[snow]]
            class = precipitation
        [[snowBatteryStatus]]
            class = battery
        [[snowDepth]]
            class = distance
        [[snowMoisture]]
            class = moisture
        [[snowRate]]
            class = precipitation_intensity
        [[so2]]
            class = sulphur_dioxide
        [[soilMoist1]]
            class = moisture
        [[soilMoist2]]
            class = moisture
        [[soilMoist3]]
            class = moisture
        [[soilMoist4]]
            class = moisture
        [[soilTemp1]]
            class = temperature
        [[soilTemp2]]
            class = temperature
        [[soilTemp3]]
            class = temperature
        [[soilTemp4]]
            class = temperature
        [[supplyVoltage]]
            class = voltage
        [[txBatteryStatus]]
            class = battery
        [[UV]]
        [[uvBatteryStatus]]
            class = battery
        [[windBatteryStatus]]
            class = battery
        [[windchill]]
            class = temperature
        [[windDir]]
        [[windGust]]
            class = wind_speed
        [[windGustDir]]
        [[windrun]]
        [[windSpeed]]
            class = wind_speed
    [units]
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
    """ Publish Home Assistant sensor configuration data. """
    def __init__(self, logger, name, plugin_dict, defaults_dict):
        self.logger = logger
        self.name = name
        self.plugin_dict = plugin_dict
        self.defaults_dict = defaults_dict

        self.config = configobj.ConfigObj(StringIO(CONFIG_STR))
        self.state_topics = {}
        for device_id in self.plugin_dict['devices']:
            device_config = self.plugin_dict['devices'][device_id]
            if 'device' not in device_config:
                device_config['device'] = {}
            device_config['device']['identifiers'] = device_id
            if 'components' not in device_config:
                device_config['components'] = {}
            self.state_topics[device_config['state_topic']] = {}

        self.qos = self.plugin_dict['qos']
        # ToDo: Figure out how to configure
        self.birth_topic = "homeassistant/status"
        self.lwt_topic = "homeassistant/status"

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
        for device_id in self.plugin_dict['devices']:
            new_sensor = False
            if topic in self.state_topics:
                for field in data:
                    # ToDo: temp hack to ignore None values (probably should be configured to not publish)
                    if data[field] is None:
                        continue
                    # ToDo: Maybe allow overriding certain attributes of the field, for example platform
                    if field not in self.plugin_dict['devices'][device_id]['components']:
                        new_sensor = True
                        self.state_topics[topic][field] = {}
                        value_template = '{{ value_json.' + field + ' | default(this.state) }}'
                        self.plugin_dict['devices'][device_id]['components'][field] = {
                            'platform': 'sensor',
                            'value_template': value_template,
                            'unique_id': field,
                            'name': self.defaults_dict['Labels']['Generic'].get(field, field),
                        }
                        (unit, _) = weewx.units.getStandardUnitType(data['usUnits'], field)
                        unit_of_measurement = None
                        if unit:
                            unit_of_measurement = self.config['units'].get(unit)
                            if unit_of_measurement:
                                self.plugin_dict['devices'][device_id]['components'][field]['unit_of_measurement'] = \
                                    unit_of_measurement
                        device_class = self.config['device_data'].get(field, {}).get('class')
                        if device_class and unit_of_measurement is not None:
                            self.plugin_dict['devices'][device_id]['components'][field]['device_class'] = device_class

                if new_sensor:
                    payload = json.dumps(self.plugin_dict['devices'][device_id])
                    topic = 'homeassistant/device/ea334450945afc/config'
                    mqtt_message_info = mqtt_client.publish(topic, payload, qos=0, retain=False)
                    self.logger.logdbg(f"publishing: {mqtt_message_info.mid} {topic}")

        self.logger.logdbg("done")

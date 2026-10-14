#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

"""Closed sets of valid Home Assistant values, for validating the
   DEFAULT_COMPONENT_DATA table in user.mqttconfigha.

   Home Assistant silently drops discovery config with an unknown
   device_class or state_class, so a typo in the table disables the
   entity instead of failing loudly. Validate every table entry against
   these sets instead of eyeballing it.

   Source: https://developers.home-assistant.io/docs/core/entity/sensor/
"""

VALID_DEVICE_CLASSES = frozenset({
    'atmospheric_pressure',
    'battery',
    'carbon_dioxide',
    'carbon_monoxide',
    'distance',
    'enum',
    'humidity',
    'illuminance',
    'irradiance',
    'moisture',
    'nitrogen_dioxide',
    'ozone',
    'pm1',
    'pm10',
    'pm25',
    'precipitation',
    'precipitation_intensity',
    'sound_pressure',
    'sulphur_dioxide',
    'temperature',
    'timestamp',
    'voltage',
    'wind_direction',
    'wind_speed',
})

VALID_STATE_CLASSES = frozenset({
    'measurement',
    'measurement_angle',
    'total',
    'total_increasing',
})

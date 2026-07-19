#
#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

''' Shim classes to make migrating from mqtthaconfig.py to mqttconfigha.py easier. '''

import user.mqttconfigha

import weewx  # Needed for unit tests

MQTTHomeAssistantConfig = user.mqttconfigha.MQTTConfigHA

# The following is needed for unit tests.
DEFAULT_COMPONENT_DATA = user.mqttconfigha.DEFAULT_COMPONENT_DATA
DEFAULT_UNITS = user.mqttconfigha.DEFAULT_UNITS

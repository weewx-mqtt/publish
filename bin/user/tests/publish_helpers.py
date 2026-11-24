#
#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

"""Test helpers shared by the MQTTPublish unit and integration suites."""

import configobj
import paho.mqtt
import random

from user.tests.unit.helpers import random_string


MONITOR_KEYS = ('monitor_queue', 'monitor_on_message', 'monitor_on_connect',
                'monitor_on_disconnect', 'monitor_on_publish',
                'monitor_record_update', 'monitor_on_weewx_data')


def create_monitor_config(**overrides):
    """ Build the seven-key monitor config, with per-test overrides. """
    config = dict.fromkeys(MONITOR_KEYS)
    config.update(overrides)
    return config


def create_publisher_config(protocol_string, **overrides):
    """ Build a publisher config with typical defaults, with per-test overrides. """
    config_dict = {
        'protocol': getattr(paho.mqtt.client, protocol_string, 0),
        'clientid': random_string(),
        'log_mqtt': random.choice([True, False]),
        'username': None,
        'password': None,
        'host': random_string(),
        'port': random.randint(1, 65535),
        'keepalive': random.randint(1, 30),
        'min_delay': 1,
        'max_delay': 120,
    }
    config_dict.update(overrides)
    return configobj.ConfigObj(config_dict)

#
#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

"""Test helpers shared by the MQTTPublish unit and integration suites."""


MONITOR_KEYS = ('monitor_queue', 'monitor_on_message', 'monitor_on_connect',
                'monitor_on_disconnect', 'monitor_on_publish',
                'monitor_record_update', 'monitor_on_weewx_data')


def create_monitor_config(**overrides):
    """ Build the seven-key monitor config, with per-test overrides. """
    config = dict.fromkeys(MONITOR_KEYS)
    config.update(overrides)
    return config

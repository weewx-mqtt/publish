#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring

import queue
import shutil
import time
import types
import unittest

import configobj
import paho.mqtt.client as mqtt

from integhelpers import BROKER_HOST, MosquittoBroker, make_observer, random_string, wait_for

import user.mqttcommon
import user.mqttpublish

TOPIC = 'weewx/integ/reconnect'


def make_publisher(port):
    """ A real Publisher, connected to the test broker. """
    config = configobj.ConfigObj({
        'protocol': mqtt.MQTTv311,
        'clientid': f"publisher-{random_string(8)}",
        'log_mqtt': False,
        'username': None,
        'password': None,
        'host': BROKER_HOST,
        'port': port,
        'keepalive': 60,
        'min_delay': 1,
        'max_delay': 4,
    })
    monitor_config = {
        'monitor_queue': None,
        'monitor_on_message': None,
        'monitor_on_connect': None,
        'monitor_on_publish': None,
        'monitor_record_update': None,
        'monitor_on_weewx_data': None,
    }
    plugin_manager = types.SimpleNamespace(callbacks={
        'on_mqtt_connect': {'immediate': {}, 'delay': {}},
        'on_mqtt_disconnect': {'immediate': {}, 'delay': {}},
        'on_mqtt_message': {'immediate': {}, 'delay': {}},
        'on_mqtt_publish': {'immediate': {}, 'delay': {}},
        'mqtt_publish': {'immediate': {}, 'delay': {}},
        'update_record': {'immediate': {}, 'delay': {}},
    })
    # Stands in for the service; Publisher only reads its 'process' flag when a startup connect fails.
    service = types.SimpleNamespace(process=True)

    return user.mqttpublish.Publisher(queue.Queue(), plugin_manager, service, config, monitor_config)


@unittest.skipUnless(shutil.which('mosquitto'), 'mosquitto is not installed.')
class TestReconnect(unittest.TestCase):
    def test_publish_reconnects_when_broker_restarts(self):
        broker = MosquittoBroker()
        self.addCleanup(broker.cleanup)
        broker.start()

        observer, received = make_observer(broker.port, TOPIC)
        self.addCleanup(observer.disconnect)
        self.addCleanup(observer.loop_stop)

        publisher = make_publisher(broker.port)
        self.addCleanup(publisher.client.disconnect)
        self.addCleanup(publisher.client.loop_stop)

        wait_for(lambda: publisher.connected, 'The publisher does not connect.')

        publisher.publish_message(time.time(), 1, False, TOPIC, 'before')
        wait_for(lambda: 'before' in received, 'The publish is not received.')

        # The broker dies; the publisher must notice and mark itself disconnected.
        broker.stop()
        wait_for(lambda: not publisher.connected, 'The publisher does not notice the broker is gone.')

        # The broker comes back; paho's network loop must reconnect on its own.
        broker.start()
        wait_for(lambda: publisher.connected, 'The publisher does not reconnect.')

        # And the next publish must go through.
        publisher.publish_message(time.time(), 1, False, TOPIC, 'after')
        wait_for(lambda: 'after' in received, 'The publish after reconnecting is not received.')


if __name__ == '__main__':
    unittest.main()

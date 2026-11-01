#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring

import os
import queue
import random
import shutil
import socket
import string
import subprocess
import tempfile
import time
import types
import unittest

import configobj
import paho.mqtt.client as mqtt

import user.mqttcommon
import user.mqttpublish

BROKER_HOST = '127.0.0.1'
TOPIC = 'weewx/integ/reconnect'


def random_string(length=32):
    return ''.join([random.choice(string.ascii_letters + string.digits) for _ in range(length)])


class MosquittoBroker():
    """ A throwaway mosquitto broker the test owns, so it can be killed and restarted. """
    def __init__(self):
        with socket.socket() as sock:
            sock.bind((BROKER_HOST, 0))
            self.port = sock.getsockname()[1]
        self.directory = tempfile.mkdtemp(prefix='weewx-mqtt-integ-')
        self.process = None

    def start(self):
        config_path = os.path.join(self.directory, 'mosquitto.conf')
        with open(config_path, 'w', encoding='utf-8') as config_file:
            config_file.write(f"listener {self.port} {BROKER_HOST}\nallow_anonymous true\n")
        self.process = subprocess.Popen(['mosquitto', '-c', config_path],  # pylint: disable=consider-using-with
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.wait_until_listening()

    def stop(self):
        if self.process is not None:
            self.process.kill()
            self.process.wait()
            self.process = None

    def cleanup(self):
        self.stop()
        shutil.rmtree(self.directory, ignore_errors=True)

    def wait_until_listening(self, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection((BROKER_HOST, self.port), timeout=1):
                    return
            except OSError:
                time.sleep(0.1)
        raise AssertionError('The mosquitto broker did not start.')


def make_observer(port):
    """ A minimal subscriber, used to verify end-to-end delivery. """
    api = user.mqttcommon.select_api(mqtt.MQTTv311)
    received = []
    client = user.mqttcommon.create_client(api, client_id=f"observer-{random_string(8)}",
                                           protocol=mqtt.MQTTv311, userdata=received)
    user.mqttcommon.configure_reconnect_delay(client, min_delay=1, max_delay=4)

    # The on_connect signature differs between the paho api variants; the *_args absorbs the difference.
    def on_connect(client, _userdata, *_args):
        client.subscribe(TOPIC, qos=1)

    def on_message(_client, userdata, message):
        userdata.append(message.payload.decode('utf-8'))

    client.on_connect = on_connect
    client.on_message = on_message
    user.mqttcommon.connect(client, api, host=BROKER_HOST, port=port, keepalive=60)
    client.loop_start()
    return client, received


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
        'monitor_record_update': None,
        'monitor_on_weewx_data': None,
    }
    plugin_manager = types.SimpleNamespace(callbacks={
        'on_mqtt_connect': {'immediate': {}, 'delay': {}},
        'on_mqtt_message': {'immediate': {}, 'delay': {}},
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

        observer, received = make_observer(broker.port)
        self.addCleanup(observer.disconnect)
        self.addCleanup(observer.loop_stop)

        publisher = make_publisher(broker.port)
        self.addCleanup(publisher.client.disconnect)
        self.addCleanup(publisher.client.loop_stop)

        self._wait_for(lambda: publisher.connected, 'The publisher does not connect.')

        publisher.publish_message(time.time(), 1, False, TOPIC, 'before')
        self._wait_for(lambda: 'before' in received, 'The publish is not received.')

        # The broker dies; the publisher must notice and mark itself disconnected.
        broker.stop()
        self._wait_for(lambda: not publisher.connected, 'The publisher does not notice the broker is gone.')

        # The broker comes back; paho's network loop must reconnect on its own.
        broker.start()
        self._wait_for(lambda: publisher.connected, 'The publisher does not reconnect.')

        # And the next publish must go through.
        publisher.publish_message(time.time(), 1, False, TOPIC, 'after')
        self._wait_for(lambda: 'after' in received, 'The publish after reconnecting is not received.')

    @staticmethod
    def _wait_for(condition, failure_message, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if condition():
                return
            time.sleep(0.1)
        raise AssertionError(failure_message)


if __name__ == '__main__':
    unittest.main()

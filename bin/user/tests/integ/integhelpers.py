#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
""" A throwaway broker and helpers for the integration tests. """

# pylint: disable=wrong-import-order

import os
import random
import shutil
import socket
import string
import subprocess
import tempfile
import threading
import time

import paho.mqtt.client as mqtt

import user.mqttcommon

BROKER_HOST = '127.0.0.1'


def random_string(length=32):
    return ''.join([random.choice(string.ascii_letters + string.digits) for _ in range(length)])


def wait_for(condition, failure_message, timeout=60):
    """ Wait for a condition, failing the test when it does not happen. """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return
        time.sleep(0.1)
    raise AssertionError(failure_message)


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


def make_observer(port, topic):
    """ A minimal subscriber, used to verify end-to-end delivery. """
    api = user.mqttcommon.select_api(mqtt.MQTTv311)
    received = []
    subscribed = threading.Event()
    client = user.mqttcommon.create_client(api, client_id=f"observer-{random_string(8)}",
                                           protocol=mqtt.MQTTv311, userdata=received)
    user.mqttcommon.configure_reconnect_delay(client, min_delay=1, max_delay=4)

    # The callback signatures differ between the paho api variants; the *_args absorbs the difference.
    def on_connect(client, _userdata, *_args):
        client.subscribe(topic, qos=1)

    def on_subscribe(_client, _userdata, _mid, *_args):
        subscribed.set()

    def on_message(_client, userdata, message):
        userdata.append(message.payload.decode('utf-8'))

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    user.mqttcommon.connect(client, api, host=BROKER_HOST, port=port, keepalive=60)
    client.loop_start()
    if not subscribed.wait(10):
        raise AssertionError('The observer did not subscribe.')
    return client, received

#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
""" An automatic resend after a reconnect, against a real broker. """

# pylint: disable=wrong-import-order

import queue
import shutil
import tempfile
import time
import types
import unittest

import configobj
import paho.mqtt.client as mqtt
import weedb

from integhelpers import BROKER_HOST, MosquittoBroker, make_observer, random_string, wait_for

import user.mqttpublish
import user.mqttmessagetracker

TOPIC = 'weewx/integ/resend-on-connect'
TABLE = 'mqtt_message_tracker'


def make_config(port):
    """ The MQTTPublish configuration for the test publisher. """
    return configobj.ConfigObj({
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


def make_tracker(logger_queue, mqtt_config, temp_dir):
    """ A real tracker, writing to a throwaway database. """
    config_dict = configobj.ConfigObj({
        'WEEWX_ROOT': temp_dir,
        'DataBindings': {
            'tracker_binding': {'database': 'tracker'},
        },
        'Databases': {
            'tracker': {
                'driver': 'weedb.sqlite',
                'database_name': 'tracker.sdb',
                'SQLITE_ROOT': temp_dir,
            },
        },
    })
    plugin_dict = configobj.ConfigObj({
        'data_binding': 'tracker_binding',
        'resend': {'enable': True},
        'topics': {TOPIC: {}},
    })
    return user.mqttmessagetracker.MQTTMessageTracker(
        logger_queue, {}, 'MQTTMessageTracker', plugin_dict, mqtt_config,
        {TOPIC: {'qos': 1}}, {'config_dict': config_dict})


def make_publisher(config, tracker, logger_queue):
    """ A real Publisher with the tracker's callbacks. """
    callbacks = {
        'on_weewx_data': {'immediate': {}, 'delay': {}},
        'on_mqtt_connect': {'immediate': {}, 'delay': {}},
        'on_mqtt_disconnect': {'immediate': {}, 'delay': {}},
        'on_mqtt_message': {'immediate': {}, 'delay': {}},
        'on_mqtt_publish': {'immediate': {}, 'delay': {}},
        'mqtt_publish': {'immediate': {}, 'delay': {}},
        'update_record': {'immediate': {}, 'delay': {}},
    }
    for callback in tracker.get_callbacks():
        for name, spec in callback.items():
            callbacks[name][spec['timing']]['tracker'] = spec['callback']

    monitor_config = {
        'monitor_queue': None,
        'monitor_on_message': None,
        'monitor_on_connect': None,
        'monitor_on_disconnect': None,
        'monitor_on_publish': None,
        'monitor_record_update': None,
        'monitor_on_weewx_data': None,
    }
    plugin_manager = types.SimpleNamespace(callbacks=callbacks)
    # Stands in for the service; Publisher only reads its 'process' flag when a startup connect fails.
    service = types.SimpleNamespace(process=True)
    return user.mqttpublish.Publisher(logger_queue, plugin_manager, service, config, monitor_config)


@unittest.skipUnless(shutil.which('mosquitto'), 'mosquitto is not installed.')
class TestResendOnConnect(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.temp_dir.cleanup)
        self.database_dict = {
            'driver': 'weedb.sqlite',
            'database_name': 'tracker.sdb',
            'SQLITE_ROOT': self.temp_dir.name,
        }

    def _rows(self):
        """ Read the tracker table, or an empty list before it exists. """
        try:
            connection = weedb.connect(self.database_dict)
        except weedb.DatabaseError:
            return []
        try:
            return user.mqttmessagetracker.fetch_rows(connection, TABLE)
        except weedb.DatabaseError:
            return []
        finally:
            connection.close()

    def _wait_for_rows(self, predicate, timeout=60):
        """ Wait for the tracker rows to match, returning them. """
        deadline = time.time() + timeout
        while time.time() < deadline:
            rows = self._rows()
            if predicate(rows):
                return rows
            time.sleep(0.1)
        self.fail("The tracker did not reach the expected state.")

    def test_resends_a_failed_message_after_reconnect(self):
        broker = MosquittoBroker()
        self.addCleanup(broker.cleanup)
        broker.start()

        observer, received = make_observer(broker.port, TOPIC)
        self.addCleanup(observer.disconnect)
        self.addCleanup(observer.loop_stop)

        logger_queue = queue.Queue()
        config = make_config(broker.port)
        tracker = make_tracker(logger_queue, config, self.temp_dir.name)
        self.addCleanup(tracker.shutdown)

        publisher = make_publisher(config, tracker, logger_queue)
        self.addCleanup(publisher.client.disconnect)
        self.addCleanup(publisher.client.loop_stop)

        wait_for(lambda: publisher.connected, 'The publisher does not connect.')

        publisher.publish_message(time.time(), 1, False, TOPIC, 'before')
        wait_for(lambda: 'before' in received, 'The first publish is not received.')
        rows = self._wait_for_rows(lambda rows: any(
            row['payload'] == 'before' and row['status'] == 'acked' for row in rows))
        before = [row for row in rows if row['payload'] == 'before'][0]

        # The broker goes away. Publish while disconnected, which paho refuses and the
        # tracker records as failed.
        broker.stop()
        wait_for(lambda: not publisher.connected, 'The publisher does not notice the broker is gone.')
        publisher.publish_message(time.time(), 1, False, TOPIC, 'missed')
        rows = self._wait_for_rows(lambda rows: any(
            row['payload'] == 'missed' and row['status'] == 'failed' for row in rows))
        missed = [row for row in rows if row['payload'] == 'missed'][0]

        # The broker returns. Paho reconnects, the tracker resends the failed message, and
        # its arrival is recorded as a new row that points at the original.
        broker.start()
        wait_for(lambda: publisher.connected, 'The publisher does not reconnect.')

        rows = self._wait_for_rows(lambda rows: any(row['origin_id'] == missed['id'] for row in rows))
        resent = [row for row in rows if row['origin_id'] == missed['id']][0]
        self.assertEqual(resent['payload'], 'missed')
        self.assertEqual(resent['attempt'], 1)
        self.assertEqual(resent['clientid'], config['clientid'])
        self.assertEqual(resent['topic'], TOPIC)

        rows = self._wait_for_rows(lambda rows: any(
            row['id'] == resent['id'] and row['status'] == 'acked' for row in rows))
        by_id = {row['id']: row for row in rows}
        self.assertEqual(by_id[resent['id']]['status'], 'acked')
        self.assertEqual(by_id[before['id']]['status'], 'acked')


if __name__ == '__main__':
    unittest.main()

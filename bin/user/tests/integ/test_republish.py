#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring

import io
import shutil
import tempfile
import time
import unittest

import paho.mqtt.client as mqtt
import weedb

from integhelpers import BROKER_HOST, MosquittoBroker, make_observer, random_string, wait_for

import user.mqttmessagetracker
import user.mqtttracker

TABLE = 'mqtt_message_tracker'
TOPIC = 'weewx/integ/republish'


@unittest.skipUnless(shutil.which('mosquitto'), 'mosquitto is not installed.')
class TestRepublish(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.temp_dir.cleanup)
        self.database_dict = {
            'driver': 'weedb.sqlite',
            'database_name': 'tracker.sdb',
            'SQLITE_ROOT': self.temp_dir.name,
        }
        weedb.create(self.database_dict)
        self.connection = weedb.connect(self.database_dict)
        self.addCleanup(self.connection.close)
        self.connection.execute(user.mqttmessagetracker.CREATE_TABLE.format(table=TABLE))

        self.broker = MosquittoBroker()
        self.addCleanup(self.broker.cleanup)
        self.broker.start()

        self.options = {
            'clientid': f'republish-{random_string(8)}',
            'protocol': mqtt.MQTTv311,
            'host': BROKER_HOST,
            'port': self.broker.port,
            'keepalive': 60,
            'username': None,
            'password': None,
            'tls': None,
            'min_delay': 1,
            'max_delay': 4,
        }

    def insert(self, payload, published_ts, status=user.mqttmessagetracker.STATUS_UNCONFIRMED):
        """ Insert a row the way the service's tracker does. """
        row_id = random_string()
        with weedb.Transaction(self.connection) as cursor:
            cursor.execute(
                f"INSERT INTO {TABLE} "
                "(id, mid, dateTime, published_ts, arrived_ts, status, unconfirmed_ts, "
                "origin_id, attempt, clientid, topic, qos, retain, rc, payload, payload_encoding) "
                "VALUES (?, ?, ?, ?, NULL, ?, NULL, NULL, NULL, NULL, ?, 1, 0, 0, ?, 'text')",
                (row_id, 1, 1700000000, published_ts, status, TOPIC, payload))
        return row_id

    def rows(self):
        cursor = self.connection.cursor()
        try:
            cursor.execute(f"SELECT {', '.join(user.mqtttracker.MESSAGE_COLUMNS)} FROM {TABLE}")
            return [dict(zip(user.mqtttracker.MESSAGE_COLUMNS, row)) for row in cursor]
        finally:
            cursor.close()

    def observe(self):
        observer, received = make_observer(self.broker.port, TOPIC)
        self.addCleanup(observer.disconnect)
        self.addCleanup(observer.loop_stop)
        return received

    def test_republishes_in_order_and_records_the_outcome(self):
        first = self.insert('first', time.time())
        second = self.insert('second', time.time() + 0.001)
        received = self.observe()

        selected, outcomes = user.mqtttracker.republish(
            self.database_dict, TABLE, self.options, dry_run=False, ack_timeout=10,
            out=io.StringIO())

        wait_for(lambda: len(received) >= 2, 'The republished messages are not received.')
        self.assertEqual(received, ['first', 'second'])
        self.assertEqual([row['id'] for row in selected], [first, second])
        self.assertEqual([outcome.status for outcome in outcomes],
                         [user.mqttmessagetracker.STATUS_CONFIRMED,
                          user.mqttmessagetracker.STATUS_CONFIRMED])

        rows = {row['id']: row for row in self.rows()}
        for origin_id in (first, second):
            republishes = [row for row in rows.values() if row['origin_id'] == origin_id]
            self.assertEqual(len(republishes), 1)
            self.assertEqual(republishes[0]['status'], user.mqttmessagetracker.STATUS_CONFIRMED)
            self.assertEqual(republishes[0]['attempt'], 1)
            self.assertEqual(republishes[0]['clientid'], self.options['clientid'])
            self.assertIsNotNone(republishes[0]['arrived_ts'])

        # The originals are never modified.
        self.assertEqual(rows[first]['status'], user.mqttmessagetracker.STATUS_UNCONFIRMED)
        self.assertIsNone(rows[first]['arrived_ts'])
        self.assertIsNone(rows[first]['attempt'])

    def test_republishes_only_the_newest_message_per_topic(self):
        self.insert('older', time.time())
        newest = self.insert('newer', time.time() + 0.001)
        received = self.observe()

        selected, outcomes = user.mqtttracker.republish(
            self.database_dict, TABLE, self.options,
            mode=user.mqtttracker.MODE_NEWEST,
            dry_run=False, ack_timeout=10, out=io.StringIO())

        wait_for(lambda: received, 'The republished message is not received.')
        self.assertEqual(received, ['newer'])
        self.assertEqual([row['id'] for row in selected], [newest])
        self.assertEqual(len(outcomes), 1)


if __name__ == '__main__':
    unittest.main()

#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name

import contextlib
import io
import os
import tempfile
import time
import unittest

import configobj
import mock

import helpers
import weedb

import user.mqttmessagetracker
import user.mqtttracker

TABLE = 'mqtt_message_tracker'


def make_row(**overrides):
    """ A row as the resend tool sees it. """
    row = {column: None for column in user.mqtttracker.MESSAGE_COLUMNS}
    row.update({
        'id': helpers.random_string(),
        'mid': 1,
        'dateTime': 1700000000,
        'sent_ts': time.time(),
        'status': user.mqttmessagetracker.STATUS_UNCONFIRMED,
        'topic': 'weather/outTemp_F',
        'qos': 0,
        'retain': 0,
        'payload': '72.5',
        'payload_encoding': 'text',
    })
    row.update(overrides)
    return row


class FakeMessageInfo:
    """ The part of paho's MQTTMessageInfo the tool uses. """

    def __init__(self, mid, rc=0):
        self.mid = mid
        self.rc = rc


class FakeClient:
    """ Stands in for RepublishClient. """

    def __init__(self, ack=True, rc=0):
        self.ack = ack
        self.rc = rc
        self.published = []
        self.connected = False
        self.closed = False

    def connect(self):
        self.connected = True

    def publish(self, topic, payload, qos, retain):
        self.published.append((topic, payload, qos, retain))
        return FakeMessageInfo(len(self.published), self.rc)

    def wait_for_ack(self, _mid):
        return time.time() if self.ack else None

    def close(self):
        self.closed = True


class DatabaseTestCase(unittest.TestCase):
    """ A real SQLite tracker database. """

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

    def rows(self):
        cursor = self.connection.cursor()
        try:
            cursor.execute(f"SELECT {', '.join(user.mqtttracker.MESSAGE_COLUMNS)} FROM {TABLE} "
                           "ORDER BY sent_ts, id")
            return [dict(zip(user.mqtttracker.MESSAGE_COLUMNS, row)) for row in cursor]
        finally:
            cursor.close()

    def insert_original(self, row, mid=1):
        """ Insert a row the way the service's tracker does. """
        with weedb.Transaction(self.connection) as cursor:
            cursor.execute(
                f"INSERT INTO {TABLE} "
                "(id, mid, dateTime, sent_ts, arrived_ts, status, unconfirmed_ts, "
                "origin_id, attempt, clientid, topic, qos, retain, rc, payload, payload_encoding) "
                "VALUES (?, ?, ?, ?, NULL, ?, NULL, NULL, NULL, NULL, ?, ?, ?, 0, ?, ?)",
                (row['id'], mid, row['dateTime'], row['sent_ts'], row['status'], row['topic'],
                 row['qos'], row['retain'], row['payload'], row['payload_encoding']))
        return row['id']

    def insert(self, row, mid=1, rc=0, sent_ts=None, clientid='republish'):
        return user.mqtttracker.insert_attempt(
            self.connection, TABLE, row, mid, rc, time.time() if sent_ts is None else sent_ts, clientid)

    def assert_row(self, row_id, **expected):
        row = {candidate['id']: candidate for candidate in self.rows()}[row_id]
        for key, value in expected.items():
            self.assertEqual(row[key], value, key)
        return row


class TestReadConfig(unittest.TestCase):
    def test_missing_file(self):
        with self.assertRaises(user.mqtttracker.RepublishConfigError):
            user.mqtttracker.read_config('/does/not/exist/weewx.conf')

    def test_reads_the_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:  # pylint: disable=consider-using-with
            config_file = os.path.join(temp_dir, 'weewx.conf')
            with open(config_file, 'w', encoding='utf-8') as file_object:
                file_object.write("[MQTTPublish]\n    host = broker\n")

            config = user.mqtttracker.read_config(config_file)

            self.assertEqual(config['MQTTPublish']['host'], 'broker')


class TestRepublishConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.temp_dir.cleanup)

        self.database_dict = {
            'driver': 'weedb.sqlite',
            'database_name': 'tracker.sdb',
            'SQLITE_ROOT': self.temp_dir.name,
        }
        self.config_dict = configobj.ConfigObj({
            'WEEWX_ROOT': self.temp_dir.name,
            'DataBindings': {
                'tracker_binding': {'database': 'tracker'},
                'other_binding': {'database': 'tracker'},
            },
            'Databases': {'tracker': self.database_dict},
            'MQTTPublish': {'host': 'broker', 'port': 1884, 'clientid': 'the-service'},
            'MQTTMessageTracker': {'data_binding': 'tracker_binding', 'table': 'custom_tracker'},
        })

    def test_resolves_the_plugin_section(self):
        database_dict, table, options = user.mqtttracker.republish_config(self.config_dict)

        self.assertEqual(database_dict['database_name'], 'tracker.sdb')
        self.assertEqual(table, 'custom_tracker')
        self.assertEqual(options['host'], 'broker')
        self.assertEqual(options['port'], 1884)

    def test_overrides_the_binding_and_table(self):
        _, table, _ = user.mqtttracker.republish_config(
            self.config_dict, data_binding='other_binding', table='other_tracker')

        self.assertEqual(table, 'other_tracker')

    def test_missing_plugin_section(self):
        with self.assertRaises(user.mqtttracker.RepublishConfigError):
            user.mqtttracker.republish_config(self.config_dict, plugin_section='Missing')

    def test_missing_data_binding(self):
        del self.config_dict['MQTTMessageTracker']['data_binding']

        with self.assertRaises(user.mqtttracker.RepublishConfigError):
            user.mqtttracker.republish_config(self.config_dict)

    def test_invalid_table(self):
        with self.assertRaises(user.mqtttracker.RepublishConfigError):
            user.mqtttracker.republish_config(self.config_dict, table='bad name')

    def test_never_reuses_the_service_clientid(self):
        _, _, options = user.mqtttracker.republish_config(self.config_dict)

        self.assertTrue(options['clientid'].startswith('MQTTPublish-republish-'))
        self.assertNotEqual(options['clientid'], 'the-service')

    def test_clientid_override(self):
        _, _, options = user.mqtttracker.republish_config(self.config_dict, clientid='republish-client')

        self.assertEqual(options['clientid'], 'republish-client')


class TestSelectMessages(unittest.TestCase):
    def test_defaults_to_error_statuses(self):
        rows = [make_row(sent_ts=1000.0),
                make_row(sent_ts=1000.0, status=user.mqttmessagetracker.STATUS_FAILED)]

        selected = user.mqtttracker.select_messages(rows, now=2000)

        self.assertEqual(sorted(row['status'] for row in selected),
                         sorted([user.mqttmessagetracker.STATUS_UNCONFIRMED,
                                 user.mqttmessagetracker.STATUS_FAILED]))

    def test_failed_status(self):
        rows = [make_row(sent_ts=1000.0),
                make_row(sent_ts=1000.0, status=user.mqttmessagetracker.STATUS_FAILED)]

        selected = user.mqtttracker.select_messages(
            rows, statuses=[user.mqttmessagetracker.STATUS_FAILED], now=2000)

        self.assertEqual([row['status'] for row in selected],
                         [user.mqttmessagetracker.STATUS_FAILED])

    def test_since(self):
        old = make_row(sent_ts=100.0)
        new = make_row(sent_ts=1500.0)

        selected = user.mqtttracker.select_messages([old, new], since=1000, now=2000)

        self.assertEqual([row['id'] for row in selected], [new['id']])

    def test_since_zero_selects_everything(self):
        rows = [make_row(sent_ts=100.0), make_row(sent_ts=1500.0, topic='weather/outHumidity')]

        selected = user.mqtttracker.select_messages(rows, since=0, now=2000)

        self.assertEqual(len(selected), 2)

    def test_default_selects_every_age(self):
        rows = [make_row(sent_ts=100.0), make_row(sent_ts=1500.0, topic='weather/outHumidity')]

        selected = user.mqtttracker.select_messages(rows, now=2000)

        self.assertEqual(len(selected), 2)

    def test_topic_glob(self):
        out_temp = make_row(topic='weather/outTemp_F', sent_ts=1000.0)
        out_humidity = make_row(topic='weather/outHumidity', sent_ts=1000.0)

        selected = user.mqtttracker.select_messages([out_temp, out_humidity], topic='weather/outTemp*', now=2000)

        self.assertEqual([row['id'] for row in selected], [out_temp['id']])

    def test_newest_per_topic(self):
        older = make_row(sent_ts=1000.0)
        newer = make_row(sent_ts=1500.0)
        other_topic = make_row(sent_ts=900.0, topic='weather/outHumidity')

        selected = user.mqtttracker.select_messages([older, newer, other_topic], now=2000)

        self.assertEqual([row['id'] for row in selected], [other_topic['id'], newer['id']])

    def test_all_disables_newest_per_topic(self):
        older = make_row(sent_ts=1000.0)
        newer = make_row(sent_ts=1500.0)

        selected = user.mqtttracker.select_messages([older, newer], newest_per_topic=False, now=2000)

        self.assertEqual([row['id'] for row in selected], [older['id'], newer['id']])

    def test_superseded_reports_the_rows_a_newer_publish_hides(self):
        unconfirmed = make_row(sent_ts=1000.0)
        confirmed = make_row(sent_ts=1500.0, status=user.mqttmessagetracker.STATUS_CONFIRMED)

        selected = user.mqtttracker.select_messages([unconfirmed, confirmed], now=2000)
        stale = user.mqtttracker.superseded([unconfirmed, confirmed], now=2000)

        self.assertEqual(selected, [])
        self.assertEqual([row['id'] for row in stale], [unconfirmed['id']])

    def test_superseded_ignores_a_failed_row(self):
        unconfirmed = make_row(sent_ts=1000.0)
        failed = make_row(sent_ts=1500.0, status=user.mqttmessagetracker.STATUS_FAILED)

        self.assertEqual(user.mqtttracker.superseded([unconfirmed, failed], now=2000), [])

    def test_a_failed_row_does_not_hide_an_older_unconfirmed_row(self):
        unconfirmed = make_row(sent_ts=1000.0)
        failed = make_row(sent_ts=1500.0, status=user.mqttmessagetracker.STATUS_FAILED)

        selected = user.mqtttracker.select_messages([unconfirmed, failed], now=2000)

        self.assertEqual([row['id'] for row in selected], [unconfirmed['id'], failed['id']])

    def test_confirmed_resend_excludes_the_origin(self):
        origin = make_row(sent_ts=1000.0)
        confirmed_resend = make_row(sent_ts=1000.0, origin_id=origin['id'], attempt=1,
                                    status=user.mqttmessagetracker.STATUS_CONFIRMED)

        selected = user.mqtttracker.select_messages([origin, confirmed_resend], now=2000)

        self.assertEqual(selected, [])

    def test_force_includes_the_origin(self):
        origin = make_row(sent_ts=1000.0)
        confirmed_resend = make_row(sent_ts=1000.0, origin_id=origin['id'], attempt=1,
                                    status=user.mqttmessagetracker.STATUS_CONFIRMED)

        selected = user.mqtttracker.select_messages([origin, confirmed_resend], force=True, now=2000)

        self.assertEqual([row['id'] for row in selected], [origin['id']])

    def test_failed_resend_does_not_exclude_the_origin(self):
        origin = make_row(sent_ts=1000.0)
        failed_resend = make_row(sent_ts=1000.0, origin_id=origin['id'], attempt=1,
                                 status=user.mqttmessagetracker.STATUS_FAILED)

        selected = user.mqtttracker.select_messages([origin, failed_resend], now=2000)

        self.assertEqual([row['id'] for row in selected], [origin['id']])

    def test_one_message_per_chain(self):
        origin = make_row(sent_ts=1000.0)
        first = make_row(sent_ts=1100.0, origin_id=origin['id'], attempt=1,
                         status=user.mqttmessagetracker.STATUS_FAILED)
        second = make_row(sent_ts=1200.0, origin_id=origin['id'], attempt=2,
                          status=user.mqttmessagetracker.STATUS_FAILED)

        selected = user.mqtttracker.select_messages([origin, first, second], now=2000)

        self.assertEqual([row['id'] for row in selected], [origin['id']])

    def test_a_sent_resend_keeps_the_message_out_of_the_queue(self):
        origin = make_row(sent_ts=1000.0)
        sent_resend = make_row(sent_ts=1100.0, origin_id=origin['id'], attempt=1,
                               status=user.mqttmessagetracker.STATUS_SENT)

        selected = user.mqtttracker.select_messages([origin, sent_resend], now=2000)

        self.assertEqual(selected, [])

    def test_since_uses_the_last_attempt(self):
        origin = make_row(sent_ts=100.0)
        failed_resend = make_row(sent_ts=1500.0, origin_id=origin['id'], attempt=1,
                                 status=user.mqttmessagetracker.STATUS_FAILED)

        selected = user.mqtttracker.select_messages([origin, failed_resend], since=1000, now=2000)

        self.assertEqual([row['id'] for row in selected], [origin['id']])

    def test_limit_keeps_the_newest_and_orders_oldest_first(self):
        rows = [make_row(sent_ts=float(index), topic=f'weather/{index}') for index in range(1, 6)]

        selected = user.mqtttracker.select_messages(rows, limit=2, now=2000)

        self.assertEqual([row['sent_ts'] for row in selected], [4.0, 5.0])

    def test_zero_limit_selects_everything(self):
        rows = [make_row(sent_ts=float(index), topic=f'weather/{index}') for index in range(1, 4)]

        selected = user.mqtttracker.select_messages(rows, limit=0, now=2000)

        self.assertEqual(len(selected), 3)


class TestDecodePayload(unittest.TestCase):
    def test_text(self):
        self.assertEqual(user.mqtttracker.decode_payload(make_row()), '72.5')

    def test_hex(self):
        row = make_row(payload='616263', payload_encoding='hex')

        self.assertEqual(user.mqtttracker.decode_payload(row), b'abc')

    def test_none(self):
        self.assertIsNone(user.mqtttracker.decode_payload(make_row(payload=None, payload_encoding=None)))


class TestInsertAttempt(DatabaseTestCase):
    def test_inserts_a_sent_row(self):
        row = make_row()
        self.insert_original(row)

        row_id, attempt, status = self.insert(row, mid=7)

        self.assertEqual(status, user.mqttmessagetracker.STATUS_SENT)
        self.assertEqual(attempt, 1)
        inserted = self.assert_row(
            row_id,
            mid=7,
            status=user.mqttmessagetracker.STATUS_SENT,
            origin_id=row['id'],
            attempt=1,
            clientid='republish',
            topic=row['topic'],
            payload=row['payload'],
            payload_encoding='text')
        self.assertIsNone(inserted['arrived_ts'])
        self.assertIsNone(inserted['unconfirmed_ts'])

    def test_inserts_a_failed_row(self):
        row = make_row()
        self.insert_original(row)

        _, _, status = self.insert(row, rc=4)

        self.assertEqual(status, user.mqttmessagetracker.STATUS_FAILED)
        self.assertEqual([candidate['rc'] for candidate in self.rows()], [0, 4])

    def test_flat_origin_across_resends(self):
        origin = make_row()
        self.insert_original(origin)

        _, first_attempt, _ = self.insert(origin)
        resend = make_row(origin_id=origin['id'], attempt=1)
        _, second_attempt, _ = self.insert(resend)

        self.assertEqual(first_attempt, 1)
        self.assertEqual(second_attempt, 2)
        self.assertEqual([row['origin_id'] for row in self.rows()[1:]], [origin['id'], origin['id']])

    def test_attempts_are_numbered_per_origin(self):
        first = make_row()
        second = make_row(topic='weather/outHumidity')
        self.insert_original(first)
        self.insert_original(second)

        self.insert(first)
        self.insert(second)

        self.assertEqual(sorted(row['attempt'] for row in self.rows()[2:]), [1, 1])


class TestUpdateAttempt(DatabaseTestCase):
    def test_confirmed(self):
        row_id, _, _ = self.insert(make_row())

        user.mqtttracker.update_attempt(
            self.connection, TABLE, row_id,
            user.mqttmessagetracker.STATUS_CONFIRMED, 1234.5)

        self.assert_row(row_id, status=user.mqttmessagetracker.STATUS_CONFIRMED, arrived_ts=1234.5)

    def test_unconfirmed(self):
        row_id, _, _ = self.insert(make_row())

        user.mqtttracker.update_attempt(
            self.connection, TABLE, row_id,
            user.mqttmessagetracker.STATUS_UNCONFIRMED, 1234.5)

        self.assert_row(row_id, status=user.mqttmessagetracker.STATUS_UNCONFIRMED, unconfirmed_ts=1234.5)


class TestRepublishMessage(DatabaseTestCase):
    def test_confirmed(self):
        row = make_row()
        client = FakeClient(ack=True)

        outcome = user.mqtttracker.republish_message(client, self.connection, TABLE, row, 'republish')

        self.assertEqual(outcome.status, user.mqttmessagetracker.STATUS_CONFIRMED)
        self.assertEqual(client.published, [('weather/outTemp_F', '72.5', 0, False)])
        stored = self.rows()[0]
        self.assertEqual(stored['status'], user.mqttmessagetracker.STATUS_CONFIRMED)
        self.assertIsNotNone(stored['arrived_ts'])
        self.assertIsNone(stored['unconfirmed_ts'])

    def test_unconfirmed(self):
        client = FakeClient(ack=False)

        outcome = user.mqtttracker.republish_message(client, self.connection, TABLE, make_row(), 'republish')

        self.assertEqual(outcome.status, user.mqttmessagetracker.STATUS_UNCONFIRMED)
        stored = self.rows()[0]
        self.assertEqual(stored['status'], user.mqttmessagetracker.STATUS_UNCONFIRMED)
        self.assertIsNotNone(stored['unconfirmed_ts'])

    def test_failed_publish_does_not_wait_for_an_ack(self):
        client = FakeClient(ack=True, rc=4)

        outcome = user.mqtttracker.republish_message(client, self.connection, TABLE, make_row(), 'republish')

        self.assertEqual(outcome.status, user.mqttmessagetracker.STATUS_FAILED)
        self.assertEqual(self.rows()[0]['rc'], 4)

    def test_hex_payload_is_published_as_bytes(self):
        row = make_row(payload='616263', payload_encoding='hex')
        client = FakeClient()

        user.mqtttracker.republish_message(client, self.connection, TABLE, row, 'republish')

        self.assertEqual(client.published[0][1], b'abc')

    def test_none_payload(self):
        row = make_row(payload=None, payload_encoding=None)
        client = FakeClient()

        user.mqtttracker.republish_message(client, self.connection, TABLE, row, 'republish')

        self.assertIsNone(client.published[0][1])

    def test_undecodable_payload(self):
        row = make_row(payload='not hex', payload_encoding='hex')

        with self.assertRaises(user.mqtttracker.RepublishConfigError):
            user.mqtttracker.republish_message(FakeClient(), self.connection, TABLE, row, 'republish')


class TestRepublish(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.options = {
            'clientid': 'republish-client',
            'protocol': 4,
        }
        self.out = io.StringIO()

    def test_dry_run_writes_nothing(self):
        self.insert_original(make_row())

        selected, outcomes = user.mqtttracker.republish(
            self.database_dict, TABLE, self.options, dry_run=True, out=self.out)

        self.assertEqual(len(selected), 1)
        self.assertEqual(outcomes, [])
        self.assertEqual(len(self.rows()), 1)
        self.assertIn('1 message(s) selected', self.out.getvalue())

    def test_nothing_selected(self):
        selected, outcomes = user.mqtttracker.republish(
            self.database_dict, TABLE, self.options, dry_run=False, out=self.out)

        self.assertEqual(selected, [])
        self.assertEqual(outcomes, [])
        self.assertIn('No messages match the selection.', self.out.getvalue())

    def test_a_stale_row_is_reported(self):
        # An unconfirmed message that a newer publish on the same topic made stale.
        self.insert_original(make_row(sent_ts=time.time() - 86400, payload='stale'))
        self.insert_original(make_row(sent_ts=time.time(), payload='newer',
                                      status=user.mqttmessagetracker.STATUS_CONFIRMED))

        selected, _ = user.mqtttracker.republish(
            self.database_dict, TABLE, self.options, dry_run=True, out=self.out)

        self.assertEqual(selected, [])
        self.assertIn('use --all to resend them', self.out.getvalue())

    def test_all_resends_a_stale_row(self):
        self.insert_original(make_row(sent_ts=time.time() - 86400, payload='stale'))
        self.insert_original(make_row(sent_ts=time.time(), payload='newer',
                                      status=user.mqttmessagetracker.STATUS_CONFIRMED))

        selected, _ = user.mqtttracker.republish(
            self.database_dict, TABLE, self.options, dry_run=True, newest_per_topic=False,
            out=self.out)

        self.assertEqual([row['payload'] for row in selected], ['stale'])

    def test_publishes_and_records(self):
        self.insert_original(make_row())
        client = FakeClient()

        with mock.patch('user.mqtttracker.RepublishClient', return_value=client) as client_class:
            _, outcomes = user.mqtttracker.republish(
                self.database_dict, TABLE, self.options, dry_run=False, out=self.out)

        client_class.assert_called_once()
        self.assertTrue(client.connected)
        self.assertTrue(client.closed)
        self.assertEqual([outcome.status for outcome in outcomes],
                         [user.mqttmessagetracker.STATUS_CONFIRMED])
        resends = [row for row in self.rows() if row['origin_id'] is not None]
        self.assertEqual(len(resends), 1)
        self.assertEqual(resends[0]['status'], user.mqttmessagetracker.STATUS_CONFIRMED)
        self.assertIn('confirmed', self.out.getvalue())

    def test_missing_database_is_a_config_error(self):
        weedb.drop(self.database_dict)

        with self.assertRaises(user.mqtttracker.RepublishConfigError):
            user.mqtttracker.republish(self.database_dict, TABLE, self.options, out=self.out)


class TestRun(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.temp_dir.cleanup)

        self.database_dict = {
            'driver': 'weedb.sqlite',
            'database_name': 'tracker.sdb',
            'SQLITE_ROOT': self.temp_dir.name,
        }
        weedb.create(self.database_dict)
        connection = weedb.connect(self.database_dict)
        try:
            connection.execute(user.mqttmessagetracker.CREATE_TABLE.format(table=TABLE))
        finally:
            connection.close()

        self.config_file = os.path.join(self.temp_dir.name, 'weewx.conf')
        config = configobj.ConfigObj({
            'WEEWX_ROOT': self.temp_dir.name,
            'DataBindings': {'tracker_binding': {'database': 'tracker'}},
            'Databases': {'tracker': self.database_dict},
            'MQTTPublish': {'host': 'localhost', 'port': 1883},
            'MQTTMessageTracker': {'data_binding': 'tracker_binding'},
        })
        config.filename = self.config_file
        config.write()

        self.out = io.StringIO()
        self.err = io.StringIO()

    def run_tool(self, *args):
        options = user.mqtttracker.build_parser().parse_args(['--config', self.config_file, 'republish', *args])
        return user.mqtttracker.run(options, out=self.out, err=self.err)

    def add_unconfirmed(self):
        connection = weedb.connect(self.database_dict)
        try:
            row_id, _, _ = user.mqtttracker.insert_attempt(
                connection, TABLE, make_row(), 1, 0, time.time(), 'republish')
            user.mqtttracker.update_attempt(
                connection, TABLE, row_id,
                user.mqttmessagetracker.STATUS_UNCONFIRMED)
        finally:
            connection.close()

    def test_dry_run_exits_zero(self):
        self.add_unconfirmed()

        self.assertEqual(self.run_tool(), 0)
        self.assertIn('message(s) selected', self.out.getvalue())

    def test_publish_exits_zero_when_confirmed(self):
        self.add_unconfirmed()
        client = FakeClient()

        with mock.patch('user.mqtttracker.RepublishClient', return_value=client):
            self.assertEqual(self.run_tool('--publish'), 0)

    def test_publish_exits_one_when_unconfirmed(self):
        self.add_unconfirmed()
        client = FakeClient(ack=False)

        with mock.patch('user.mqtttracker.RepublishClient', return_value=client):
            self.assertEqual(self.run_tool('--publish'), 1)

    def test_connect_failure_exits_one(self):
        self.add_unconfirmed()
        client = FakeClient()
        client.connect = mock.Mock(side_effect=user.mqtttracker.RepublishConnectError('no broker'))

        with mock.patch('user.mqtttracker.RepublishClient', return_value=client):
            self.assertEqual(self.run_tool('--publish'), 1)

        self.assertIn('no broker', self.err.getvalue())

    def test_missing_config_exits_two(self):
        options = user.mqtttracker.build_parser().parse_args(['--config', '/does/not/exist/weewx.conf', 'republish'])

        self.assertEqual(user.mqtttracker.run(options, out=self.out, err=self.err), 2)
        self.assertIn('Unable to read the config file', self.err.getvalue())

    def test_missing_section_exits_two(self):
        self.assertEqual(self.run_tool('--plugin-section', 'Missing'), 2)
        self.assertIn('[Missing]', self.err.getvalue())

    def test_unconfirmed_exits_two(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                user.mqtttracker.build_parser().parse_args(['--config', self.config_file, 'republish', '--status', 'confirmed'])

    def test_statuses(self):
        options = user.mqtttracker.build_parser().parse_args(
            ['--config', self.config_file, 'republish', '--status', 'failed,unconfirmed'])

        self.assertEqual(options.status, [user.mqttmessagetracker.STATUS_FAILED,
                                          user.mqttmessagetracker.STATUS_UNCONFIRMED])


class TestBuildParser(unittest.TestCase):
    def test_defaults(self):
        options = user.mqtttracker.build_parser().parse_args(['--config', 'weewx.conf', 'republish'])

        self.assertFalse(options.publish)
        self.assertFalse(options.all)
        self.assertFalse(options.force)
        self.assertEqual(options.plugin_section, 'MQTTMessageTracker')
        self.assertEqual(options.status, [user.mqttmessagetracker.STATUS_FAILED,
                                          user.mqttmessagetracker.STATUS_UNCONFIRMED])
        self.assertIsNone(options.since)
        self.assertEqual(options.limit, 100)
        self.assertIsNone(options.topic)
        self.assertIsNone(options.clientid)


if __name__ == '__main__':
    helpers.run_tests()

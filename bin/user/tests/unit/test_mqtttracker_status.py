#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name

import io
import os
import tempfile
import unittest

import configobj
import weedb

import helpers

import user.mqttmessagetracker
import user.mqtttracker

TABLE = 'mqtt_message_tracker'
STATUS = user.mqttmessagetracker


def make_row(**overrides):
    """ A row as the status command sees it. """
    row = {column: None for column in user.mqttmessagetracker.MESSAGE_COLUMNS}
    row.update({
        'id': helpers.random_string(),
        'mid': 1,
        'dateTime': 1700000000,
        'sent_ts': 1000.0,
        'status': STATUS.STATUS_FAILED,
        'topic': 'weather/outTemp_F',
        'qos': 0,
        'retain': 0,
        'payload': '72.5',
        'payload_encoding': 'text',
    })
    row.update(overrides)
    return row


def tracker_config(temp_dir, database_dict):
    """ A config with the tracker section, binding and database. """
    return configobj.ConfigObj({
        'WEEWX_ROOT': temp_dir,
        'DataBindings': {'tracker_binding': {'database': 'tracker'}},
        'Databases': {'tracker': database_dict},
        'MQTTMessageTracker': {
            'data_binding': 'tracker_binding',
            'topics': {'weather/outTemp_F': {}},
        },
    })


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

        self.out = io.StringIO()
        self.err = io.StringIO()

    def insert(self, row):
        with weedb.Transaction(self.connection) as cursor:
            cursor.execute(
                f"INSERT INTO {TABLE} ({', '.join(user.mqttmessagetracker.MESSAGE_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in user.mqttmessagetracker.MESSAGE_COLUMNS)})",
                tuple(row[column] for column in user.mqttmessagetracker.MESSAGE_COLUMNS))
        return row['id']

    def run_tool(self, *args):
        config_file = os.path.join(self.temp_dir.name, 'weewx.conf')
        config = tracker_config(self.temp_dir.name, self.database_dict)
        config.filename = config_file
        config.write()
        options = user.mqtttracker.build_parser().parse_args(
            ['--config', config_file, 'status', *args])
        return user.mqtttracker.run(options, out=self.out, err=self.err)


class TestStatus(DatabaseTestCase):
    def test_summary_shows_the_outcome(self):
        original = make_row(sent_ts=1000.0)
        resend = make_row(sent_ts=1100.0, status=STATUS.STATUS_CONFIRMED,
                          origin_id=original['id'], attempt=1, arrived_ts=1200.0)
        unresolved = make_row(sent_ts=2000.0, status=STATUS.STATUS_UNCONFIRMED)
        self.insert(original)
        self.insert(resend)
        self.insert(unresolved)

        self.assertEqual(self.run_tool(), 0)

        self.assertIn(original['id'], self.out.getvalue())
        self.assertIn(unresolved['id'], self.out.getvalue())
        self.assertIn('sent', self.out.getvalue())
        self.assertIn('not resent', self.out.getvalue())

    def test_unresolved_hides_messages_with_a_confirmed_resend(self):
        original = make_row(sent_ts=1000.0)
        resend = make_row(sent_ts=1100.0, status=STATUS.STATUS_CONFIRMED,
                          origin_id=original['id'], attempt=1, arrived_ts=1200.0)
        unresolved = make_row(sent_ts=2000.0, status=STATUS.STATUS_UNCONFIRMED)
        self.insert(original)
        self.insert(resend)
        self.insert(unresolved)

        self.assertEqual(self.run_tool('--unresolved'), 0)

        self.assertNotIn(original['id'], self.out.getvalue())
        self.assertIn(unresolved['id'], self.out.getvalue())

    def test_message_shows_the_original_and_its_resends(self):
        original = make_row(sent_ts=1000.0)
        resend = make_row(sent_ts=1100.0, status=STATUS.STATUS_CONFIRMED,
                          origin_id=original['id'], attempt=1, arrived_ts=1200.0)
        self.insert(original)
        self.insert(resend)

        self.assertEqual(self.run_tool('--message', original['id']), 0)

        self.assertIn(original['id'], self.out.getvalue())
        self.assertIn(resend['id'], self.out.getvalue())
        self.assertIn('attempt=1', self.out.getvalue())

    def test_unknown_message_exits_one(self):
        self.insert(make_row())

        self.assertEqual(self.run_tool('--message', 'does-not-exist'), 1)
        self.assertIn('No rows found for message does-not-exist.', self.out.getvalue())

    def test_limit(self):
        for index in range(3):
            self.insert(make_row(id=helpers.random_string(), sent_ts=float(index)))

        self.assertEqual(self.run_tool('--limit', '2'), 0)
        self.assertIn('2 failed or unconfirmed message(s)', self.out.getvalue())

    def test_missing_config_exits_two(self):
        options = user.mqtttracker.build_parser().parse_args(
            ['--config', '/does/not/exist/weewx.conf', 'status'])

        self.assertEqual(user.mqtttracker.run(options, out=self.out, err=self.err), 2)
        self.assertIn('Unable to read the config file', self.err.getvalue())


class TestBuildParser(unittest.TestCase):
    def test_defaults(self):
        options = user.mqtttracker.build_parser().parse_args(
            ['--config', 'weewx.conf', 'status'])

        self.assertIsNone(options.message)
        self.assertFalse(options.unresolved)
        self.assertIsNone(options.topic)
        self.assertEqual(options.limit, 100)
        self.assertEqual(options.plugin_section, 'MQTTMessageTracker')
        self.assertEqual(options.command, 'status')


if __name__ == '__main__':
    helpers.run_tests()

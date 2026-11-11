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
import mock
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
    def test_summary_shows_the_unresolved_outcome(self):
        original = make_row(sent_ts=1000.0)
        resend = make_row(sent_ts=1100.0, status=STATUS.STATUS_CONFIRMED,
                          origin_id=original['id'], attempt=1, arrived_ts=1200.0)
        unresolved = make_row(sent_ts=2000.0, status=STATUS.STATUS_UNCONFIRMED)
        self.insert(original)
        self.insert(resend)
        self.insert(unresolved)

        self.assertEqual(self.run_tool(), 0)

        self.assertNotIn(original['id'], self.out.getvalue())
        self.assertIn(unresolved['id'], self.out.getvalue())
        self.assertIn('ORIGINAL STATUS', self.out.getvalue())
        self.assertIn('ORIGINALLY SENT', self.out.getvalue())
        self.assertIn('FINAL STATUS', self.out.getvalue())
        self.assertIn('unconfirmed', self.out.getvalue())

    def test_status_filter_shows_sent_rows(self):
        failed = make_row(status=STATUS.STATUS_FAILED)
        sent = make_row(status=STATUS.STATUS_SENT)
        self.insert(failed)
        self.insert(sent)

        self.assertEqual(self.run_tool('--status', 'sent'), 0)

        self.assertIn(sent['id'], self.out.getvalue())
        self.assertNotIn(failed['id'], self.out.getvalue())
        self.assertIn('1 message(s) with status sent', self.out.getvalue())

    def test_status_filter_can_show_no_rows(self):
        self.insert(make_row(status=STATUS.STATUS_FAILED))

        self.assertEqual(self.run_tool('--status', 'sent'), 0)

        self.assertIn('No messages with status sent.', self.out.getvalue())

    def test_default_includes_sent_and_excludes_confirmed(self):
        failed = make_row(status=STATUS.STATUS_FAILED)
        unconfirmed = make_row(status=STATUS.STATUS_UNCONFIRMED)
        sent = make_row(status=STATUS.STATUS_SENT)
        confirmed = make_row(status=STATUS.STATUS_CONFIRMED)
        for row in (failed, unconfirmed, sent, confirmed):
            self.insert(row)

        self.assertEqual(self.run_tool(), 0)

        output = self.out.getvalue()
        for row in (failed, unconfirmed, sent):
            self.assertIn(row['id'], output)
        self.assertNotIn(confirmed['id'], output)
        self.assertIn('3 not confirmed message(s)', output)

    def test_summary_shows_one_row_per_chain(self):
        original = make_row(status=STATUS.STATUS_FAILED, sent_ts=1000.0)
        first = make_row(status=STATUS.STATUS_SENT, sent_ts=1100.0,
                         origin_id=original['id'], attempt=1)
        second = make_row(status=STATUS.STATUS_SENT, sent_ts=1200.0,
                          origin_id=original['id'], attempt=2)
        for row in (original, first, second):
            self.insert(row)

        self.assertEqual(self.run_tool(), 0)

        output = self.out.getvalue()
        self.assertIn('1 not confirmed message(s)', output)
        self.assertIn(original['id'], output)
        self.assertNotIn(first['id'], output)
        self.assertNotIn(second['id'], output)
        line = [row for row in output.splitlines() if original['id'] in row][0]
        self.assertEqual(line.split()[-3:], ['2', '0', 'sent'])

    def test_summary_anchors_an_orphaned_chain_at_the_oldest_resend(self):
        original_id = helpers.random_string()
        first = make_row(status=STATUS.STATUS_SENT, sent_ts=1100.0,
                         origin_id=original_id, attempt=1)
        second = make_row(status=STATUS.STATUS_SENT, sent_ts=1200.0,
                          origin_id=original_id, attempt=2)
        self.insert(first)
        self.insert(second)

        self.assertEqual(self.run_tool(), 0)

        output = self.out.getvalue()
        self.assertIn(first['id'], output)
        self.assertNotIn(second['id'], output)
        line = [row for row in output.splitlines() if first['id'] in row][0]
        self.assertEqual(line.split()[-3:], ['2', '0', 'sent'])

    def test_status_confirmed_shows_a_delivered_chain(self):
        original = make_row(sent_ts=1000.0)
        resend = make_row(sent_ts=1100.0, status=STATUS.STATUS_CONFIRMED,
                          origin_id=original['id'], attempt=1, arrived_ts=1200.0)
        self.insert(original)
        self.insert(resend)

        self.assertEqual(self.run_tool('--status', 'confirmed'), 0)

        output = self.out.getvalue()
        self.assertIn(original['id'], output)
        self.assertNotIn(resend['id'], output)
        line = [row for row in output.splitlines() if original['id'] in row][0]
        self.assertEqual(line.split()[-3:], ['1', '1', 'confirmed'])

    def test_a_delivered_chain_is_not_a_failed_message(self):
        original = make_row(sent_ts=1000.0, status=STATUS.STATUS_FAILED)
        resend = make_row(sent_ts=1100.0, status=STATUS.STATUS_CONFIRMED,
                          origin_id=original['id'], attempt=1, arrived_ts=1200.0)
        self.insert(original)
        self.insert(resend)

        self.assertEqual(self.run_tool('--status', 'failed'), 0)

        self.assertIn('No messages with status failed.', self.out.getvalue())

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

    def test_message_accepts_a_resend_id(self):
        original = make_row(sent_ts=1000.0)
        resend = make_row(sent_ts=1100.0, status=STATUS.STATUS_CONFIRMED,
                          origin_id=original['id'], attempt=1, arrived_ts=1200.0)
        self.insert(original)
        self.insert(resend)

        self.assertEqual(self.run_tool('--message', resend['id']), 0)

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
        self.assertIn('2 not confirmed message(s)', self.out.getvalue())

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
        self.assertIsNone(options.topic)
        self.assertEqual(options.status, ['failed', 'unconfirmed', 'sent'])
        self.assertEqual(options.limit, 100)
        self.assertEqual(options.plugin_section, 'MQTTMessageTracker')
        self.assertEqual(options.command, 'status')


class TestBootstrap(unittest.TestCase):
    def test_defaults_bindirs_reads_weewx_bindir(self):
        with tempfile.NamedTemporaryFile('w', delete=False) as file_object:
            file_object.write('WEEWX_PYTHON=python3\n'
                              'WEEWX_BINDIR=/usr/share/weewx\n')
        self.addCleanup(os.unlink, file_object.name)

        self.assertEqual(user.mqtttracker._defaults_bindirs(file_object.name), ['/usr/share/weewx'])

    def test_defaults_bindirs_ignores_a_missing_file(self):
        self.assertEqual(user.mqtttracker._defaults_bindirs('/does/not/exist'), [])

    def test_weewx_bindir_prefers_the_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.makedirs(os.path.join(temp_dir, 'weewx'))
            with mock.patch.dict(os.environ, {'WEEWX_BINDIR': temp_dir}):
                self.assertEqual(user.mqtttracker._weewx_bindir(), temp_dir)


if __name__ == '__main__':
    helpers.run_tests()

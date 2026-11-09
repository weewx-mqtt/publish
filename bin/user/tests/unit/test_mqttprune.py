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
import weedb

import helpers

import user.mqttmessagetracker
import user.mqttprune

TABLE = 'mqtt_message_tracker'
STATUS = user.mqttmessagetracker


def make_row(**overrides):
    """ A row as the prune tool sees it. """
    row = {column: None for column in user.mqttmessagetracker.MESSAGE_COLUMNS}
    row.update({
        'id': helpers.random_string(),
        'mid': 1,
        'dateTime': 1700000000,
        'sent_ts': 1000.0,
        'status': STATUS.STATUS_UNCONFIRMED,
        'topic': 'weather/outTemp_F',
        'qos': 0,
        'retain': 0,
        'payload': '72.5',
        'payload_encoding': 'text',
    })
    row.update(overrides)
    return row


def tracker_config(temp_dir, database_dict, error_retention=100, topics=None):
    """ A config with the tracker section, binding and database. """
    return configobj.ConfigObj({
        'WEEWX_ROOT': temp_dir,
        'DataBindings': {'tracker_binding': {'database': 'tracker'}},
        'Databases': {'tracker': database_dict},
        'MQTTMessageTracker': {
            'data_binding': 'tracker_binding',
            'error_retention': error_retention,
            'topics': {'weather/outTemp_F': {}} if topics is None else topics,
        },
    })


class TestSelectRows(unittest.TestCase):
    def test_defaults_to_unconfirmed(self):
        rows = [make_row(sent_ts=100.0),
                make_row(sent_ts=100.0, status=STATUS.STATUS_FAILED)]

        selected = user.mqttprune.select_rows(rows, default_retention=100, now=1000)

        self.assertEqual([row['status'] for row in selected], [STATUS.STATUS_UNCONFIRMED])

    def test_failed_status(self):
        rows = [make_row(sent_ts=100.0),
                make_row(sent_ts=100.0, status=STATUS.STATUS_FAILED)]

        selected = user.mqttprune.select_rows(
            rows, statuses=[STATUS.STATUS_FAILED], default_retention=100, now=1000)

        self.assertEqual([row['status'] for row in selected], [STATUS.STATUS_FAILED])

    def test_sent_and_confirmed_are_never_selected(self):
        rows = [make_row(sent_ts=100.0, status=STATUS.STATUS_SENT),
                make_row(sent_ts=100.0, status=STATUS.STATUS_CONFIRMED)]

        selected = user.mqttprune.select_rows(rows, default_retention=100, now=1000)

        self.assertEqual(selected, [])

    def test_the_topic_retention_overrides_the_default(self):
        rows = [make_row(sent_ts=925.0, topic='default'),
                make_row(sent_ts=925.0, topic='short')]

        selected = user.mqttprune.select_rows(
            rows, topic_retention={'short': 50}, default_retention=100, now=1000)

        self.assertEqual([row['topic'] for row in selected], ['short'])

    def test_an_unlisted_topic_uses_the_default_retention(self):
        rows = [make_row(sent_ts=800.0, topic='unlisted')]

        selected = user.mqttprune.select_rows(
            rows, topic_retention={'other': 50}, default_retention=100, now=1000)

        self.assertEqual([row['topic'] for row in selected], ['unlisted'])

    def test_a_retention_of_zero_keeps_the_topic(self):
        rows = [make_row(sent_ts=1.0, topic='keep')]

        selected = user.mqttprune.select_rows(
            rows, topic_retention={'keep': 0}, default_retention=100, now=1000)

        self.assertEqual(selected, [])

    def test_older_than_overrides_the_configured_retention(self):
        rows = [make_row(sent_ts=500.0, topic='keep')]

        selected = user.mqttprune.select_rows(
            rows, topic_retention={'keep': 0}, default_retention=100, older_than=100, now=1000)

        self.assertEqual([row['topic'] for row in selected], ['keep'])

    def test_older_than_zero_selects_every_matching_row(self):
        rows = [make_row(sent_ts=999.0, topic='keep'),
                make_row(sent_ts=999.0, topic='keep', status=STATUS.STATUS_FAILED),
                make_row(sent_ts=999.0, status=STATUS.STATUS_SENT)]

        selected = user.mqttprune.select_rows(
            rows, statuses=[STATUS.STATUS_UNCONFIRMED, STATUS.STATUS_FAILED],
            topic_retention={'keep': 0}, default_retention=0, older_than=0, now=1000)

        self.assertEqual(sorted(row['status'] for row in selected),
                         sorted([STATUS.STATUS_UNCONFIRMED, STATUS.STATUS_FAILED]))

    def test_topic_glob(self):
        rows = [make_row(sent_ts=100.0, topic='weather/outTemp_F'),
                make_row(sent_ts=100.0, topic='weather/outHumidity')]

        selected = user.mqttprune.select_rows(
            rows, topic='weather/outTemp*', default_retention=100, now=1000)

        self.assertEqual([row['topic'] for row in selected], ['weather/outTemp_F'])

    def test_limit_keeps_the_oldest(self):
        rows = [make_row(sent_ts=float(index), topic=f'weather/{index}') for index in range(1, 6)]

        selected = user.mqttprune.select_rows(rows, default_retention=100, limit=2, now=1000)

        self.assertEqual([row['sent_ts'] for row in selected], [1.0, 2.0])

    def test_zero_limit_selects_everything(self):
        rows = [make_row(sent_ts=float(index), topic=f'weather/{index}') for index in range(1, 4)]

        selected = user.mqttprune.select_rows(rows, default_retention=100, limit=0, now=1000)

        self.assertEqual(len(selected), 3)


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

    def rows(self):
        cursor = self.connection.cursor()
        try:
            cursor.execute(f"SELECT {', '.join(user.mqttmessagetracker.MESSAGE_COLUMNS)} FROM {TABLE} "
                           "ORDER BY sent_ts, id")
            return [dict(zip(user.mqttmessagetracker.MESSAGE_COLUMNS, row)) for row in cursor]
        finally:
            cursor.close()

    def options(self, *args):
        return user.mqttprune.build_parser().parse_args(['weewx.conf', *args])


class TestDeleteRows(DatabaseTestCase):
    def test_deletes_the_selected_rows(self):
        old = make_row(sent_ts=time.time() - 1000)
        new = make_row(sent_ts=time.time(), topic='weather/outHumidity')
        self.insert(old)
        self.insert(new)

        selected = user.mqttprune.select_rows(self.rows(), default_retention=100)

        deleted = user.mqttprune.delete_rows(self.connection, TABLE, selected)

        self.assertEqual(deleted, 1)
        self.assertEqual([row['id'] for row in self.rows()], [new['id']])

    def test_skips_a_row_whose_status_changed(self):
        row = make_row(sent_ts=time.time() - 1000)
        self.insert(row)
        selected = user.mqttprune.select_rows(self.rows(), default_retention=100)

        with weedb.Transaction(self.connection) as cursor:
            cursor.execute(f"UPDATE {TABLE} SET status = ? WHERE id = ?",
                           (STATUS.STATUS_FAILED, row['id']))
        deleted = user.mqttprune.delete_rows(self.connection, TABLE, selected)

        self.assertEqual(deleted, 0)
        self.assertEqual(len(self.rows()), 1)

    def test_is_idempotent(self):
        self.insert(make_row(sent_ts=time.time() - 1000))
        selected = user.mqttprune.select_rows(self.rows(), default_retention=100)

        user.mqttprune.delete_rows(self.connection, TABLE, selected)
        user.mqttprune.delete_rows(self.connection, TABLE, selected)

        self.assertEqual(self.rows(), [])


class TestPrune(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.config_dict = tracker_config(self.temp_dir.name, self.database_dict)

    def test_dry_run_writes_nothing(self):
        self.insert(make_row(sent_ts=time.time() - 1000))

        selected = user.mqttprune.prune(self.config_dict, self.options(), out=self.out)

        self.assertEqual(len(selected), 1)
        self.assertEqual(len(self.rows()), 1)
        self.assertIn('1 message(s) selected', self.out.getvalue())

    def test_deletes_the_selection(self):
        old = make_row(sent_ts=time.time() - 1000)
        self.insert(old)

        user.mqttprune.prune(self.config_dict, self.options('--delete'), out=self.out)

        self.assertEqual(self.rows(), [])
        self.assertIn('Deleted 1 row(s).', self.out.getvalue())

    def test_nothing_selected(self):
        self.insert(make_row(sent_ts=time.time()))

        selected = user.mqttprune.prune(self.config_dict, self.options('--delete'), out=self.out)

        self.assertEqual(selected, [])
        self.assertEqual(len(self.rows()), 1)
        self.assertIn('No messages match the selection.', self.out.getvalue())

    def test_per_topic_error_retention(self):
        config_dict = tracker_config(self.temp_dir.name, self.database_dict,
                                     error_retention=1000,
                                     topics={'weather/outTemp_F': {'error_retention': 10}})
        old = make_row(sent_ts=time.time() - 1000)
        self.insert(old)

        selected = user.mqttprune.prune(config_dict, self.options(), out=self.out)

        self.assertEqual([row['id'] for row in selected], [old['id']])


class TestRun(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.config_file = os.path.join(self.temp_dir.name, 'weewx.conf')
        config = tracker_config(self.temp_dir.name, self.database_dict)
        config.filename = self.config_file
        config.write()

    def run_tool(self, *args):
        options = user.mqttprune.build_parser().parse_args([self.config_file, *args])
        return user.mqttprune.run(options, out=self.out, err=self.err)

    def test_dry_run_exits_zero(self):
        self.insert(make_row(sent_ts=time.time() - 1000))

        self.assertEqual(self.run_tool(), 0)
        self.assertEqual(len(self.rows()), 1)

    def test_delete_exits_zero(self):
        self.insert(make_row(sent_ts=time.time() - 1000))

        self.assertEqual(self.run_tool('--delete'), 0)
        self.assertEqual(self.rows(), [])

    def test_missing_config_exits_two(self):
        options = user.mqttprune.build_parser().parse_args(['/does/not/exist/weewx.conf'])

        self.assertEqual(user.mqttprune.run(options, out=self.out, err=self.err), 2)
        self.assertIn('Unable to read the config file', self.err.getvalue())

    def test_missing_section_exits_two(self):
        self.assertEqual(self.run_tool('--plugin-section', 'Missing'), 2)
        self.assertIn('[Missing]', self.err.getvalue())

    def test_invalid_status_exits_two(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                user.mqttprune.build_parser().parse_args([self.config_file, '--status', 'sent'])

    def test_missing_table_exits_two(self):
        self.connection.execute(f"DROP TABLE {TABLE}")

        self.assertEqual(self.run_tool(), 2)
        self.assertIn('Unable to use the message tracker table', self.err.getvalue())


class TestBuildParser(unittest.TestCase):
    def test_defaults(self):
        options = user.mqttprune.build_parser().parse_args(['weewx.conf'])

        self.assertFalse(options.delete)
        self.assertEqual(options.plugin_section, 'MQTTMessageTracker')
        self.assertEqual(options.status, [STATUS.STATUS_UNCONFIRMED])
        self.assertIsNone(options.older_than)
        self.assertIsNone(options.topic)
        self.assertEqual(options.limit, 100)

    def test_statuses(self):
        options = user.mqttprune.build_parser().parse_args(
            ['weewx.conf', '--status', 'failed,unconfirmed'])

        self.assertEqual(options.status, [STATUS.STATUS_FAILED, STATUS.STATUS_UNCONFIRMED])


if __name__ == '__main__':
    helpers.run_tests()

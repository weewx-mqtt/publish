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
import user.mqtttracker

TABLE = 'mqtt_message_tracker'
STATUS = user.mqttmessagetracker


def make_row(**overrides):
    """ A row as the prune tool sees it. """
    row = {column: None for column in user.mqttmessagetracker.MESSAGE_COLUMNS}
    row.update({
        'id': helpers.random_string(),
        'mid': 1,
        'dateTime': 1700000000,
        'published_ts': 1000.0,
        'status': STATUS.STATUS_UNCONFIRMED,
        'topic': 'weather/outTemp_F',
        'qos': 0,
        'retain': 0,
        'payload': '72.5',
        'payload_encoding': 'text',
    })
    row.update(overrides)
    return row


def confirmed_row(**overrides):
    """ A row as the prune tool sees a confirmed message. """
    options = {'status': STATUS.STATUS_CONFIRMED}
    options.update(overrides)
    return make_row(**options)


def tracker_config(temp_dir, database_dict, error_retention=100, confirmed_retention=100,
                   topics=None):
    """ A config with the tracker section, binding and database. """
    return configobj.ConfigObj({
        'WEEWX_ROOT': temp_dir,
        'DataBindings': {'tracker_binding': {'database': 'tracker'}},
        'Databases': {'tracker': database_dict},
        'MQTTMessageTracker': {
            'data_binding': 'tracker_binding',
            'error_retention': error_retention,
            'confirmed_retention': confirmed_retention,
            'topics': {'weather/outTemp_F': {}} if topics is None else topics,
        },
    })


class TestSelectChains(unittest.TestCase):
    def test_defaults_to_confirmed(self):
        rows = [confirmed_row(published_ts=100.0),
                make_row(published_ts=100.0),
                make_row(published_ts=100.0, status=STATUS.STATUS_FAILED)]

        selected = user.mqtttracker.select_chains(
            rows, confirmed_default_retention=100, now=1000)

        self.assertEqual([row['status'] for row in selected], [STATUS.STATUS_CONFIRMED])

    def test_failed_status(self):
        rows = [make_row(published_ts=100.0),
                make_row(published_ts=100.0, status=STATUS.STATUS_FAILED)]

        selected = user.mqtttracker.select_chains(
            rows, statuses=[STATUS.STATUS_FAILED], default_retention=100, now=1000)

        self.assertEqual([row['status'] for row in selected], [STATUS.STATUS_FAILED])

    def test_sent_is_never_selected(self):
        rows = [make_row(published_ts=100.0, status=STATUS.STATUS_INFLIGHT)]

        selected = user.mqtttracker.select_chains(
            rows, statuses=[STATUS.STATUS_FAILED, STATUS.STATUS_UNCONFIRMED],
            default_retention=100, now=1000)

        self.assertEqual(selected, [])

    def test_the_topic_retention_overrides_the_default(self):
        rows = [confirmed_row(published_ts=925.0, topic='default'),
                confirmed_row(published_ts=925.0, topic='short')]

        selected = user.mqtttracker.select_chains(
            rows, confirmed_topic_retention={'short': 50}, confirmed_default_retention=100, now=1000)

        self.assertEqual([row['topic'] for row in selected], ['short'])

    def test_an_unlisted_topic_uses_the_default_retention(self):
        rows = [confirmed_row(published_ts=800.0, topic='unlisted')]

        selected = user.mqtttracker.select_chains(
            rows, confirmed_topic_retention={'other': 50}, confirmed_default_retention=100, now=1000)

        self.assertEqual([row['topic'] for row in selected], ['unlisted'])

    def test_a_retention_of_zero_keeps_the_topic(self):
        rows = [confirmed_row(published_ts=1.0, topic='keep')]

        selected = user.mqtttracker.select_chains(
            rows, confirmed_topic_retention={'keep': 0}, confirmed_default_retention=100, now=1000)

        self.assertEqual(selected, [])

    def test_older_than_overrides_the_configured_retention(self):
        rows = [confirmed_row(published_ts=500.0, topic='keep')]

        selected = user.mqtttracker.select_chains(
            rows, confirmed_topic_retention={'keep': 0}, confirmed_default_retention=100,
            older_than=100, now=1000)

        self.assertEqual([row['topic'] for row in selected], ['keep'])

    def test_older_than_zero_selects_every_matching_message(self):
        rows = [confirmed_row(published_ts=999.0, topic='keep'),
                make_row(published_ts=999.0, topic='keep', status=STATUS.STATUS_FAILED),
                make_row(published_ts=999.0, status=STATUS.STATUS_INFLIGHT)]

        selected = user.mqtttracker.select_chains(
            rows, statuses=[STATUS.STATUS_CONFIRMED, STATUS.STATUS_FAILED],
            confirmed_topic_retention={'keep': 0}, confirmed_default_retention=0,
            default_retention=0, older_than=0, now=1000)

        self.assertEqual(sorted(row['status'] for row in selected),
                         sorted([STATUS.STATUS_CONFIRMED, STATUS.STATUS_FAILED]))

    def test_topic_glob(self):
        rows = [confirmed_row(published_ts=100.0, topic='weather/outTemp_F'),
                confirmed_row(published_ts=100.0, topic='weather/outHumidity')]

        selected = user.mqtttracker.select_chains(
            rows, confirmed_default_retention=100, topic='weather/outTemp*', now=1000)

        self.assertEqual([row['topic'] for row in selected], ['weather/outTemp_F'])

    def test_limit_keeps_the_oldest(self):
        rows = [confirmed_row(published_ts=float(index), topic=f'weather/{index}')
                for index in range(1, 6)]

        selected = user.mqtttracker.select_chains(
            rows, confirmed_default_retention=100, limit=2, now=1000)

        self.assertEqual([row['published_ts'] for row in selected], [1.0, 2.0])

    def test_a_chain_is_one_message(self):
        original = make_row(published_ts=1000.0, status=STATUS.STATUS_FAILED)
        republish = make_row(
            published_ts=1100.0,
            **{'status': STATUS.STATUS_CONFIRMED, 'origin_id': original['id'], 'attempt': 1})

        selected = user.mqtttracker.select_chains(
            [original, republish], confirmed_default_retention=100, now=1300)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['id'], original['id'])
        self.assertEqual(selected[0]['status'], STATUS.STATUS_CONFIRMED)
        self.assertEqual(selected[0]['published_ts'], republish['published_ts'])

    def test_a_confirmed_chain_ignores_the_error_retention(self):
        original = make_row(published_ts=1000.0, status=STATUS.STATUS_FAILED)
        republish = make_row(
            published_ts=1100.0,
            **{'status': STATUS.STATUS_CONFIRMED, 'origin_id': original['id'], 'attempt': 1})

        selected = user.mqtttracker.select_chains(
            [original, republish], confirmed_default_retention=100, default_retention=0, now=1300)

        self.assertEqual([row['id'] for row in selected], [original['id']])

    def test_an_unresolved_chain_uses_its_last_attempt(self):
        original = make_row(published_ts=100.0, status=STATUS.STATUS_FAILED)
        republish = make_row(
            published_ts=1000.0,
            **{'status': STATUS.STATUS_FAILED, 'origin_id': original['id'], 'attempt': 1})
        args = {'statuses': [STATUS.STATUS_FAILED], 'default_retention': 100}

        kept = user.mqtttracker.select_chains([original, republish], now=1050, **args)
        selected = user.mqtttracker.select_chains([original, republish], now=1200, **args)

        self.assertEqual(kept, [])
        self.assertEqual([row['id'] for row in selected], [original['id']])

    def test_zero_limit_selects_everything(self):
        rows = [confirmed_row(published_ts=float(index), topic=f'weather/{index}')
                for index in range(1, 4)]

        selected = user.mqtttracker.select_chains(
            rows, confirmed_default_retention=100, limit=0, now=1000)

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
                           "ORDER BY published_ts, id")
            return [dict(zip(user.mqttmessagetracker.MESSAGE_COLUMNS, row)) for row in cursor]
        finally:
            cursor.close()

    def options(self, *args):
        return user.mqtttracker.build_parser().parse_args(['--config', 'weewx.conf', 'prune', *args])


class TestDeleteChains(DatabaseTestCase):
    def test_deletes_the_selected_messages(self):
        old = confirmed_row(published_ts=time.time() - 1000)
        new = confirmed_row(published_ts=time.time(), topic='weather/outHumidity')
        self.insert(old)
        self.insert(new)

        selected = user.mqtttracker.select_chains(self.rows(), confirmed_default_retention=100)

        deleted = user.mqtttracker.delete_chains(self.connection, TABLE, selected)

        self.assertEqual(deleted, 1)
        self.assertEqual([row['id'] for row in self.rows()], [new['id']])

    def test_deletes_the_rest_of_the_chain(self):
        original = make_row(published_ts=time.time() - 1000, status=STATUS.STATUS_FAILED)
        republish = make_row(published_ts=time.time() - 900, **{
            'status': STATUS.STATUS_CONFIRMED, 'origin_id': original['id'], 'attempt': 1})
        newer = confirmed_row(published_ts=time.time(), topic='weather/outHumidity')
        self.insert(original)
        self.insert(republish)
        self.insert(newer)

        selected = user.mqtttracker.select_chains(self.rows(), confirmed_default_retention=100)

        deleted = user.mqtttracker.delete_chains(self.connection, TABLE, selected)

        self.assertEqual(deleted, 2)
        self.assertEqual([row['id'] for row in self.rows()], [newer['id']])

    def test_leaves_a_sent_republish(self):
        original = confirmed_row(published_ts=time.time() - 1000)
        republish = make_row(published_ts=time.time() - 900, **{
            'status': STATUS.STATUS_INFLIGHT, 'origin_id': original['id'], 'attempt': 1})
        self.insert(original)
        self.insert(republish)

        selected = user.mqtttracker.select_chains(self.rows(), confirmed_default_retention=100)

        deleted = user.mqtttracker.delete_chains(self.connection, TABLE, selected)

        self.assertEqual(deleted, 1)
        self.assertEqual([row['id'] for row in self.rows()], [republish['id']])

    def test_deletes_an_orphaned_republish(self):
        republish = make_row(published_ts=time.time() - 1000, **{
            'status': STATUS.STATUS_CONFIRMED, 'origin_id': helpers.random_string(),
            'attempt': 1})
        self.insert(republish)

        selected = user.mqtttracker.select_chains(self.rows(), confirmed_default_retention=100)

        deleted = user.mqtttracker.delete_chains(self.connection, TABLE, selected)

        self.assertEqual(deleted, 1)
        self.assertEqual(self.rows(), [])

    def test_skips_a_message_whose_outcome_changed(self):
        row = make_row(published_ts=time.time() - 1000, status=STATUS.STATUS_FAILED)
        self.insert(row)
        selected = user.mqtttracker.select_chains(
            self.rows(), statuses=[STATUS.STATUS_FAILED], default_retention=100)

        with weedb.Transaction(self.connection) as cursor:
            cursor.execute(f"UPDATE {TABLE} SET status = ? WHERE id = ?",
                           (STATUS.STATUS_CONFIRMED, row['id']))
        deleted = user.mqtttracker.delete_chains(self.connection, TABLE, selected)

        self.assertEqual(deleted, 0)
        self.assertEqual(len(self.rows()), 1)

    def test_is_idempotent(self):
        self.insert(confirmed_row(published_ts=time.time() - 1000))
        selected = user.mqtttracker.select_chains(self.rows(), confirmed_default_retention=100)

        user.mqtttracker.delete_chains(self.connection, TABLE, selected)
        user.mqtttracker.delete_chains(self.connection, TABLE, selected)

        self.assertEqual(self.rows(), [])


class TestPrune(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.config_dict = tracker_config(self.temp_dir.name, self.database_dict)

    def test_dry_run_writes_nothing(self):
        self.insert(confirmed_row(published_ts=time.time() - 1000))

        selected = user.mqtttracker.prune(self.config_dict, self.options(), out=self.out)

        self.assertEqual(len(selected), 1)
        self.assertEqual(len(self.rows()), 1)
        self.assertIn('1 message(s) selected', self.out.getvalue())

    def test_dry_run_shows_the_row_count(self):
        original = confirmed_row(published_ts=time.time() - 1000)
        republish = make_row(published_ts=time.time() - 900, **{
            'status': STATUS.STATUS_CONFIRMED, 'origin_id': original['id'], 'attempt': 1})
        standalone = confirmed_row(published_ts=time.time() - 800)
        for row in (original, republish, standalone):
            self.insert(row)

        selected = user.mqtttracker.prune(self.config_dict, self.options(), out=self.out)

        self.assertEqual(len(selected), 2)
        self.assertIn('2 message(s) selected (3 row(s)):', self.out.getvalue())

    def test_deletes_the_selection(self):
        self.insert(confirmed_row(published_ts=time.time() - 1000))

        user.mqtttracker.prune(self.config_dict, self.options('--delete'), out=self.out)

        self.assertEqual(self.rows(), [])
        self.assertIn('Deleted 1 row(s).', self.out.getvalue())

    def test_nothing_selected(self):
        self.insert(confirmed_row(published_ts=time.time()))

        selected = user.mqtttracker.prune(self.config_dict, self.options('--delete'), out=self.out)

        self.assertEqual(selected, [])
        self.assertEqual(len(self.rows()), 1)
        self.assertIn('No messages match the selection.', self.out.getvalue())

    def test_limit_reports_the_remainder(self):
        for index in range(3):
            self.insert(confirmed_row(published_ts=time.time() - 1000 + index))

        selected = user.mqtttracker.prune(
            self.config_dict, self.options('--limit', '2'), out=self.out)

        self.assertEqual(len(selected), 2)
        self.assertIn('Selected the oldest 2 of 3 message(s); use --limit 0 to select all.',
                      self.out.getvalue())

    def test_default_prune_keeps_unresolved_messages(self):
        self.insert(make_row(published_ts=time.time() - 1000, status=STATUS.STATUS_FAILED))

        selected = user.mqtttracker.prune(
            self.config_dict, self.options('--delete'), out=self.out)

        self.assertEqual(selected, [])
        self.assertEqual(len(self.rows()), 1)

    def test_failed_status_prunes_an_unresolved_message(self):
        self.insert(make_row(published_ts=time.time() - 1000, status=STATUS.STATUS_FAILED))

        selected = user.mqtttracker.prune(
            self.config_dict, self.options('--status', 'failed', '--delete'), out=self.out)

        self.assertEqual(len(selected), 1)
        self.assertEqual(self.rows(), [])

    def test_failed_original_is_deleted_with_its_confirmed_republish(self):
        original = make_row(published_ts=time.time() - 1000, status=STATUS.STATUS_FAILED)
        republish = make_row(published_ts=time.time() - 900, **{
            'status': STATUS.STATUS_CONFIRMED, 'origin_id': original['id'], 'attempt': 1})
        self.insert(original)
        self.insert(republish)

        selected = user.mqtttracker.prune(
            self.config_dict, self.options('--delete'), out=self.out)

        self.assertEqual(len(selected), 1)
        self.assertEqual(self.rows(), [])
        self.assertIn('Deleted 2 row(s).', self.out.getvalue())

    def test_confirmed_retention(self):
        old = confirmed_row(published_ts=time.time() - 1000)
        self.insert(old)

        default_config = tracker_config(
            self.temp_dir.name, self.database_dict,
            confirmed_retention=user.mqttmessagetracker.DEFAULT_CONFIRMED_RETENTION)
        kept = user.mqtttracker.prune(default_config, self.options(), out=self.out)

        config_dict = tracker_config(self.temp_dir.name, self.database_dict, confirmed_retention=10)
        selected = user.mqtttracker.prune(config_dict, self.options(), out=self.out)

        self.assertEqual(kept, [])
        self.assertEqual([row['id'] for row in selected], [old['id']])

    def test_per_topic_confirmed_retention(self):
        config_dict = tracker_config(self.temp_dir.name, self.database_dict,
                                     confirmed_retention=1000,
                                     topics={'weather/outTemp_F': {'confirmed_retention': 10}})
        old = confirmed_row(published_ts=time.time() - 1000)
        self.insert(old)

        selected = user.mqtttracker.prune(config_dict, self.options(), out=self.out)

        self.assertEqual([row['id'] for row in selected], [old['id']])

    def test_per_topic_error_retention(self):
        config_dict = tracker_config(self.temp_dir.name, self.database_dict,
                                     error_retention=1000,
                                     topics={'weather/outTemp_F': {'error_retention': 10}})
        old = make_row(published_ts=time.time() - 1000)
        self.insert(old)

        selected = user.mqtttracker.prune(
            config_dict, self.options('--status', 'unconfirmed'), out=self.out)

        self.assertEqual([row['id'] for row in selected], [old['id']])


class TestRun(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.config_file = os.path.join(self.temp_dir.name, 'weewx.conf')
        config = tracker_config(self.temp_dir.name, self.database_dict)
        config.filename = self.config_file
        config.write()

    def run_tool(self, *args):
        options = user.mqtttracker.build_parser().parse_args(['--config', self.config_file, 'prune', *args])
        return user.mqtttracker.run(options, out=self.out, err=self.err)

    def test_dry_run_exits_zero(self):
        self.insert(confirmed_row(published_ts=time.time() - 1000))

        self.assertEqual(self.run_tool(), 0)
        self.assertEqual(len(self.rows()), 1)

    def test_delete_exits_zero(self):
        self.insert(confirmed_row(published_ts=time.time() - 1000))

        self.assertEqual(self.run_tool('--delete'), 0)
        self.assertEqual(self.rows(), [])

    def test_missing_config_exits_two(self):
        options = user.mqtttracker.build_parser().parse_args(['--config', '/does/not/exist/weewx.conf', 'prune'])

        self.assertEqual(user.mqtttracker.run(options, out=self.out, err=self.err), 2)
        self.assertIn('Unable to read the config file', self.err.getvalue())

    def test_missing_section_exits_two(self):
        self.assertEqual(self.run_tool('--plugin-section', 'Missing'), 2)
        self.assertIn('[Missing]', self.err.getvalue())

    def test_invalid_status_exits_two(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                user.mqtttracker.build_parser().parse_args(['--config', self.config_file, 'prune', '--status', 'inflight'])

    def test_missing_table_exits_two(self):
        self.connection.execute(f"DROP TABLE {TABLE}")

        self.assertEqual(self.run_tool(), 2)
        self.assertIn('Unable to use the message tracker table', self.err.getvalue())


class TestBuildParser(unittest.TestCase):
    def test_defaults(self):
        options = user.mqtttracker.build_parser().parse_args(['--config', 'weewx.conf', 'prune'])

        self.assertFalse(options.delete)
        self.assertEqual(options.plugin_section, 'MQTTMessageTracker')
        self.assertEqual(options.status, [STATUS.STATUS_CONFIRMED])
        self.assertIsNone(options.older_than)
        self.assertIsNone(options.topic)
        self.assertEqual(options.limit, 100)

    def test_statuses(self):
        options = user.mqtttracker.build_parser().parse_args(
            ['--config', 'weewx.conf', 'prune', '--status', 'failed,unconfirmed'])

        self.assertEqual(options.status, [STATUS.STATUS_FAILED, STATUS.STATUS_UNCONFIRMED])

    def test_confirmed_status(self):
        options = user.mqtttracker.build_parser().parse_args(
            ['--config', 'weewx.conf', 'prune', '--status', 'confirmed'])

        self.assertEqual(options.status, [STATUS.STATUS_CONFIRMED])


if __name__ == '__main__':
    helpers.run_tests()

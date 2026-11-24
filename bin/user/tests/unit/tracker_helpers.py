#
#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

"""Shared helpers for the MQTT tracker CLI tests."""

import io
import tempfile
import unittest

import configobj
import weedb

import user.mqttmessagetracker
import user.mqtttracker
from user.tests.unit.helpers import random_string

TABLE = 'mqtt_message_tracker'


def make_tracker_row(*, status=None, published_ts=None, **overrides):
    """ Build a tracker row; each CLI test module supplies its own defaults. """
    row = {column: None for column in user.mqttmessagetracker.MESSAGE_COLUMNS}
    row.update({
        'id': random_string(),
        'mid': 1,
        'dateTime': 1700000000,
        'published_ts': 1000.0,
        'status': user.mqttmessagetracker.STATUS_UNCONFIRMED,
        'topic': 'weather/outTemp_F',
        'qos': 0,
        'retain': 0,
        'payload': '72.5',
        'payload_encoding': 'text',
    })
    if status is not None:
        row['status'] = status
    if published_ts is not None:
        row['published_ts'] = published_ts
    row.update(overrides)
    return row


def make_tracker_config(temp_dir, database_dict, **overrides):
    """ Build a tracker config; each CLI test module supplies its own options. """
    section = {'data_binding': 'tracker_binding', 'topics': {'weather/outTemp_F': {}}}
    section.update(overrides)
    return configobj.ConfigObj({
        'WEEWX_ROOT': temp_dir,
        'DataBindings': {'tracker_binding': {'database': 'tracker'}},
        'Databases': {'tracker': database_dict},
        'MQTTMessageTracker': section,
    })


def run_tracker_tool(test_case, subcommand, config_file, *args):
    """ Parse a tracker CLI invocation and run it with the test's output streams. """
    options = user.mqtttracker.build_parser().parse_args(
        ['--config', config_file, subcommand, *args])
    return user.mqtttracker.run(options, out=test_case.out, err=test_case.err)


class TrackerDatabaseTestCase(unittest.TestCase):
    """ A real SQLite tracker database shared by the tracker CLI tests."""

    __test__ = False  # shared base; concrete subclasses set True

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

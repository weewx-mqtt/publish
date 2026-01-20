#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name
import unittest
import mock

import helpers

import configobj
import random
import time

import user.mqttpublish

class TestPublishWeeWXThread(unittest.TestCase):
    def test_update_record(self):
        mock_logger = mock.Mock()
        config = None
        topics_loop = None
        topics_archive = None
        data_queue = None

        SUT = user.mqttpublish.PublishWeeWXThread(mock_logger, config, topics_loop, topics_archive, data_queue)

        field1 = helpers.random_string()
        aggreagate1 = helpers.random_string()
        period = random.choice(list(user.mqttpublish.period_timespan.keys()))

        topic_dict = {
            'unit_system': 1,
            'format': '%s',
            'fields': {},
            'aggregates': {
                aggreagate1: {
                    'period': period,
                    'observation': helpers.random_string(),
                    'aggregation': helpers.random_string(),
                },
            },
        }

        record = {
            'dateTime': time.time(),
            'usUnits': 1,
        }

        field_value = random.random()
        updated_record = {
            field1: field_value,
            'usUnits': 1,
        }

        with mock.patch.object(user.mqttpublish.weewx.units, 'to_std_system', return_value=updated_record):
            with mock.patch.object(user.mqttpublish.weewx.xtypes, 'get_aggregate'):
                with mock.patch.object(user.mqttpublish.weewx.units, 'convertStd', return_value=[field_value]):

                    final_record = SUT.update_record(topic_dict, record)

                    expected_record = {
                        field1: str(field_value),
                        aggreagate1: str(field_value),
                        'usUnits': '1',
                    }

                    self.assertDictEqual(final_record, expected_record)

    def test_update_field(self):
        mock_logger = mock.Mock()
        config_dict = {}
        config = configobj.ConfigObj(config_dict)
        config = None
        topics_loop = {}
        topics_loop = None
        topics_archive = {}
        topics_archive = None
        data_queue_mock = mock.Mock()

        SUT = user.mqttpublish.PublishWeeWXThread(mock_logger, config, topics_loop, topics_archive, data_queue_mock)

        field1 = helpers.random_string()

        topic_dict = {
            'unit_system': 1,
            'fields': {
                field1: {
                    'unit': 'foobar',
                    'append_unit_label': True,
                    'conversion_type': 'float',
                    'format': '%s'
                }
            },
        }

        updated_record = {
            field1: random.random(),
            'usUnits': 1,
        }
        converted_value = random.random()
        unit_type = helpers.random_string()

        with mock.patch.object(user.mqttpublish.weewx.units,
                               'getStandardUnitType',
                               return_value=(unit_type, helpers.random_string())):
            with mock.patch.object(user.mqttpublish.weewx.units, 'convert', return_value=[converted_value]):

                (name, value) = SUT.update_field(topic_dict,
                                                 topic_dict['fields'][field1],
                                                 field1,
                                                 updated_record[field1],
                                                 updated_record['usUnits'])

                self.assertEqual(name, f"{field1}_{unit_type}")
                self.assertEqual(value, converted_value)

if __name__ == '__main__':
    helpers.run_tests()

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
    def test_test(self):
        mock_logger = mock.Mock()
        config_dict = {}
        config = configobj.ConfigObj(config_dict)
        config = None
        topics_loop = {}
        topics_loop = None
        topics_archive = {}
        topics_archive = None
        # data_queue = Queue.Queue()
        data_queue_mock = mock.Mock()

        SUT = user.mqttpublish.PublishWeeWXThread(mock_logger, config, topics_loop, topics_archive, data_queue_mock)

        field1 = helpers.random_string()
        # aggreagate1 = helpers.random_string()
        # period = random.choice(list(user.mqttpublish.period_timespan.keys()))

        topic_dict = {
            # 'qos': 0,
            # 'retain': False,
            # 'type': 'json',
            'unit_system': 1,
            # 'guarantee_delivery': False,
            # 'ignore': False,
            # 'append_unit_label': True,
            # 'conversion_type': 'string',
            'format': '%s',
            'fields': {
            #    field1: {
            #        'name': field1,
            #        'unit': None,
            #        'ignore': False,
            #        'publish_none_value': False,
            #        'append_unit_label': False,
            #        'conversion_type': 'string',
            #        'format_string': '%s'
            #    }
            },
            'aggregates': {
            #    aggreagate1: {
            #        'period': period,
            #        'name': aggreagate1,
            #        'unit': None,
            #        'ignore': False,
            #        'publish_none_value': False,
            #        'append_unit_label': False,
            #        'conversion_type': 'string',
            #        'format_string': '%s',
            #        'observation': helpers.random_string(),
            #        'aggregation': helpers.random_string(),
            #    },
            },
        }

        record = {
            'dateTime': time.time(),
            'usUnits': 1,
        }
        updated_record = {
            field1: random.random(),
            'usUnits': 1,
        }

        with mock.patch.object(user.mqttpublish.weewx.units, 'to_std_system', return_value=updated_record):
            with mock.patch.object(user.mqttpublish.weewx.xtypes, 'get_aggregate'):
                with mock.patch.object(user.mqttpublish.weewx.units, 'convertStd', return_value=[random.random()]):

                    final_record = SUT.update_record(topic_dict, record)
                    print(final_record)

        print("done")

    @unittest.skip("")
    def test_template(self):
        mock_logger = mock.Mock()
        config_dict = {}
        config = configobj.ConfigObj(config_dict)
        config = None
        topics_loop = {}
        topics_loop = None
        topics_archive = {}
        topics_archive = None
        # data_queue = Queue.Queue()
        data_queue_mock = mock.Mock()

        SUT = user.mqttpublish.PublishWeeWXThread(mock_logger, config, topics_loop, topics_archive, data_queue_mock)

        field1 = helpers.random_string()
        # aggreagate1 = helpers.random_string()
        # period = random.choice(list(user.mqttpublish.period_timespan.keys()))

        topic_dict = {
            # 'qos': 0,
            # 'retain': False,
            # 'type': 'json',
            'unit_system': 1,
            # 'guarantee_delivery': False,
            # 'ignore': False,
            # 'append_unit_label': True,
            # 'conversion_type': 'string',
            'format': '%s',
            'fields': {
                field1: {
            #        'name': field1,
            #        'unit': None,
            #        'ignore': False,
            #        'publish_none_value': False,
            #        'append_unit_label': False,
            #        'conversion_type': 'string',
            #        'format_string': '%s'
                }
            },
            'aggregates': {
            #    aggreagate1: {
            #        'period': period,
            #        'name': aggreagate1,
            #        'unit': None,
            #        'ignore': False,
            #        'publish_none_value': False,
            #        'append_unit_label': False,
            #        'conversion_type': 'string',
            #        'format_string': '%s',
            #        'observation': helpers.random_string(),
            #        'aggregation': helpers.random_string(),
            #    },
            },
        }

        record = {
            'dateTime': time.time(),
            'usUnits': 1,
        }
        updated_record = {
            field1: random.random(),
            'usUnits': 1,
        }

        with mock.patch.object(user.mqttpublish.weewx.units, 'to_std_system', return_value=updated_record):
            with mock.patch.object(user.mqttpublish.weewx.xtypes, 'get_aggregate'):
                with mock.patch.object(user.mqttpublish.weewx.units, 'convertStd', return_value=[random.random()]):

                    final_record = SUT.update_record(topic_dict, record)
                    print(final_record)

        print("done")

if __name__ == '__main__':
    helpers.run_tests()

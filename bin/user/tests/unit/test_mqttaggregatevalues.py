#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name

import unittest
import mock

import configobj
import copy
import time

import helpers

import user.mqttaggregatevalues

import weewx

class Test_MQTTAggregateValues(unittest.TestCase):
    def test_update_record(self):
        mock_logger = mock.Mock()
        name = helpers.random_string()
        topic = helpers.random_string()
        period = helpers.random_string()
        aggregate = helpers.random_string()
        plugin_dict = {
            'topics': {
                topic: {
                    aggregate: {
                        'observation': helpers.random_string(),
                        'aggregation': helpers.random_string(),
                        'period': period
                    }
                }
            }
        }
        weewx_dict = {
            'stn_info': mock.Mock(),
            'manager_dict': {}
        }
        plugin_config = configobj.ConfigObj(plugin_dict)

        with mock.patch('user.mqttaggregatevalues.TimeSpanProvider') as mock_timespan_provider:
            with mock.patch('user.mqttaggregatevalues.weewx.manager'):
                with mock.patch('user.mqttpublish.weewx.xtypes') as mock_xtype:
                    mock_timespan_provider.return_value.period_timespans = [period]
                    aggregate_value = helpers.random_string()
                    mock_xtype.get_aggregate.return_value = (aggregate_value, 'bar', 'foobar')
                    date_time = time.time()

                    SUT = user.mqttaggregatevalues.MQTTAggregateValues(mock_logger, name, plugin_config, {}, weewx_dict)

                    record = {
                        'dateTime': date_time
                    }
                    SUT.update_record(None, topic, record, None, None, None)

                    expected_record = copy.deepcopy(record)
                    expected_record.update({
                        aggregate: aggregate_value
                    })
                    self.assertDictEqual(record, expected_record)

    def test_update_record_aggregate_exception(self):
        mock_logger = mock.Mock()
        name = helpers.random_string()
        topic = helpers.random_string()
        period = helpers.random_string()
        aggregate = helpers.random_string()
        plugin_dict = {
            'topics': {
                topic: {
                    aggregate: {
                        'observation': helpers.random_string(),
                        'aggregation': helpers.random_string(),
                        'period': period
                    }
                }
            }
        }
        weewx_dict = {
            'stn_info': mock.Mock(),
            'manager_dict': {}
        }
        plugin_config = configobj.ConfigObj(plugin_dict)

        with mock.patch('user.mqttaggregatevalues.TimeSpanProvider') as mock_timespan_provider:
            with mock.patch('user.mqttaggregatevalues.weewx.manager'):
                with mock.patch('user.mqttpublish.weewx.xtypes') as mock_xtype:
                    mock_timespan_provider.return_value.period_timespans = [period]
                    mock_xtype.get_aggregate.side_effect = weewx.CannotCalculate
                    date_time = time.time()

                    SUT = user.mqttaggregatevalues.MQTTAggregateValues(mock_logger, name, plugin_config, {}, weewx_dict)

                    record = {
                        'dateTime': date_time
                    }
                    SUT.update_record(None, topic, record, None, None, None)

                    expected_record = copy.deepcopy(record)

                    self.assertDictEqual(record, expected_record)
                    self.assertEqual(mock_logger.logerr.call_count, 2)

    def test_get_callbacks(self):
        mock_logger = mock.Mock()
        name = helpers.random_string()
        topic = helpers.random_string()
        period = helpers.random_string()
        aggregate = helpers.random_string()
        plugin_dict = {
            'topics': {
                topic: {
                    aggregate: {
                        'observation': helpers.random_string(),
                        'aggregation': helpers.random_string(),
                        'period': period
                    }
                }
            }
        }
        weewx_dict = {
            'stn_info': mock.Mock(),
            'manager_dict': {}
        }
        plugin_config = configobj.ConfigObj(plugin_dict)

        with mock.patch('user.mqttaggregatevalues.TimeSpanProvider') as mock_timespan_provider:
            with mock.patch('user.mqttaggregatevalues.weewx.manager'):
                with mock.patch('user.mqttpublish.weewx.xtypes') as mock_xtype:
                    mock_timespan_provider.return_value.period_timespans = [period]
                    mock_xtype.get_aggregate.side_effect = weewx.CannotCalculate

                    SUT = user.mqttaggregatevalues.MQTTAggregateValues(mock_logger, name, plugin_config, {}, weewx_dict)

                    callbacks = SUT.get_callbacks()

                    expected_callbacks = [
                        {
                            'update_record': {
                                'timing': 'immediate',
                                'callback': SUT.update_record
                            },
                        },
                    ]
                    self.assertEqual(callbacks, expected_callbacks)

if __name__ == '__main__':
    helpers.run_tests()

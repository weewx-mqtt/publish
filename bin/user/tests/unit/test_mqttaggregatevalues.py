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
import datetime
import time

import helpers

import user.mqttaggregatevalues

import weewx

class Test_MQTTAggregateValues(unittest.TestCase):
    def test_update_record(self):
        mock_logger_queue = mock.Mock()
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

                    SUT = user.mqttaggregatevalues.MQTTAggregateValues(mock_logger_queue,
                                                                       None,
                                                                       name,
                                                                       plugin_config,
                                                                       None,
                                                                       {},
                                                                       weewx_dict)

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
        mock_logger_queue = mock.Mock()
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

                    SUT = user.mqttaggregatevalues.MQTTAggregateValues(mock_logger_queue,
                                                                       None,
                                                                       name,
                                                                       plugin_config,
                                                                       None,
                                                                       {},
                                                                       weewx_dict)

                    record = {
                        'dateTime': date_time
                    }
                    SUT.update_record(None, topic, record, None, None, None)

                    expected_record = copy.deepcopy(record)

                    self.assertDictEqual(record, expected_record)
                    self.assertEqual(mock_logger_queue.put.call_count, 2)

    def test_get_callbacks(self):
        mock_logger_queue = mock.Mock()
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

                    SUT = user.mqttaggregatevalues.MQTTAggregateValues(mock_logger_queue,
                                                                       None,
                                                                       name,
                                                                       plugin_config,
                                                                       None,
                                                                       {},
                                                                       weewx_dict)

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

    @staticmethod
    def _make_plugin(plugin_dict):
        logger_queue = mock.Mock()
        weewx_dict = {
            'stn_info': mock.Mock(),
            'manager_dict': {}
        }
        plugin_config = configobj.ConfigObj(plugin_dict)

        with mock.patch('user.mqttaggregatevalues.weewx.manager'):
            plugin = user.mqttaggregatevalues.MQTTAggregateValues(logger_queue,
                                                                  None,
                                                                  helpers.random_string(),
                                                                  plugin_config,
                                                                  None,
                                                                  None,
                                                                  weewx_dict)
        return plugin, logger_queue

    def test_init_disabled(self):
        plugin, logger_queue = self._make_plugin({
            'enable': False,
            'topics': {'topic': {'obs': {'observation': 'x', 'aggregation': 'avg', 'period': 'hour'}}}
        })

        self.assertFalse(plugin.enabled)
        self.assertEqual(logger_queue.put.call_count, 1)
        self.assertEqual(plugin.get_callbacks(), [])

    def test_init_invalid_period(self):
        with self.assertRaises(ValueError) as context:
            self._make_plugin({
                'topics': {'topic': {'obs': {'observation': 'x', 'aggregation': 'avg', 'period': 'bogus'}}}
            })

        self.assertEqual(str(context.exception), "Invalid 'period', bogus")

    def test_init_calculation_interval_provided(self):
        plugin, _ = self._make_plugin({
            'topics': {'topic': {'obs': {'observation': 'x', 'aggregation': 'avg',
                                         'period': 'hour', 'calculation_interval': 7}}}
        })

        self.assertEqual(plugin.plugin_dict['topics']['topic']['obs']['calculation_interval'], 7 * 60)

    def test_init_daily_adjustment(self):
        plugin, _ = self._make_plugin({
            'topics': {'topic': {'obs': {'observation': 'x', 'aggregation': 'avg', 'period': 'yesterday'}}}
        })

        expected_adjustment = datetime.datetime.now().astimezone().utcoffset().seconds - (60 * 60 * 24)
        self.assertEqual(plugin.last_calculated['topic']['obs']['adjustment'], expected_adjustment)

    def test_update_record_unknown_topic(self):
        plugin, _ = self._make_plugin({
            'topics': {'topic': {'obs': {'observation': 'outTemp', 'aggregation': 'avg', 'period': 'hour'}}}
        })

        record = {'dateTime': 1771939800}
        plugin.update_record(None, 'unknown_topic', record, None, None, None)

        self.assertEqual(record, {'dateTime': 1771939800})

    def test_update_record_disabled_aggregate(self):
        plugin, _ = self._make_plugin({
            'topics': {'topic': {
                'active': {'observation': 'outTemp', 'aggregation': 'avg', 'period': 'hour'},
                'inactive': {'observation': 'x', 'aggregation': 'avg', 'period': 'hour', 'enable': False},
            }}
        })

        with mock.patch('user.mqttaggregatevalues.weewx.xtypes') as mock_xtypes:
            mock_xtypes.get_aggregate.return_value = (42, 'unit', 'group')
            record = {'dateTime': 1771939800}
            plugin.update_record(None, 'topic', record, None, None, None)

            self.assertEqual(record['active'], 42)
            self.assertNotIn('inactive', record)
            self.assertEqual(mock_xtypes.get_aggregate.call_count, 1)

    def test_update_record_no_recalculation(self):
        plugin, _ = self._make_plugin({
            'topics': {'topic': {'obs': {'observation': 'outTemp', 'aggregation': 'avg', 'period': 'hour'}}}
        })

        with mock.patch('user.mqttaggregatevalues.weewx.xtypes') as mock_xtypes:
            mock_xtypes.get_aggregate.return_value = (42, 'unit', 'group')

            first_record = {'dateTime': 1771939800}
            plugin.update_record(None, 'topic', first_record, None, None, None)

            # A second record within the same calculation interval must reuse the
            # cached value rather than recalculating.
            second_record = {'dateTime': 1771939800}
            plugin.update_record(None, 'topic', second_record, None, None, None)

            self.assertEqual(mock_xtypes.get_aggregate.call_count, 1)
            self.assertEqual(first_record['obs'], 42)
            self.assertEqual(second_record['obs'], 42)

if __name__ == '__main__':
    helpers.run_tests()

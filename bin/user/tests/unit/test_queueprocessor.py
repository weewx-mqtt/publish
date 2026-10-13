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
import queue
import random
import threading
import time

import user.mqttpublish

class TestQueueProcessor(unittest.TestCase):
    def test_update_record(self):
        mock_logger_queue = mock.Mock()
        config = {}
        topics_loop = {}
        topics_archive = {}
        data_queue = None
        weewx_dict = {
            'config_dict': {
                'MQTTPublish': {}
            }
        }

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        SUT = user.mqttpublish.QueueProcessor(mock_logger_queue,
                                              {},
                                              weewx_dict,
                                              None,
                                              config,
                                              monitor_dict,
                                              topics_loop,
                                              topics_archive,
                                              data_queue)

        field1 = helpers.random_string()

        topic_dict = {
            'unit_system': 1,
            'format_string': '%s',
            'fields': {},
            'minimum_interval': None,
            'data_last_published': {},
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

                    final_record = SUT.update_record(topic_dict, time.time(), record)

                    expected_record = {
                        field1: str(field_value),
                        'usUnits': '1',
                    }

                    self.assertDictEqual(final_record, expected_record)

    def test_update_record_interval_end_ts(self):
        mock_logger_queue = mock.Mock()
        weewx_dict = {
            'config_dict': {
                'MQTTPublish': {}
            }
        }

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        SUT = user.mqttpublish.QueueProcessor(mock_logger_queue,
                                              {},
                                              weewx_dict,
                                              None,
                                              {},
                                              monitor_dict,
                                              {},
                                              {},
                                              None)

        field1 = helpers.random_string()
        now = 1000.0

        record = {
            'dateTime': now,
            'usUnits': 1,
        }

        updated_record = {
            field1: random.random(),
            'usUnits': 1,
        }

        topic_dict = {
            'unit_system': 1,
            'fields': {},
            'minimum_interval': 60,
            'suppression_threshold': 1.0,
            'data_last_published': {},
        }

        with mock.patch.object(user.mqttpublish.weewx.units, 'to_std_system', return_value=updated_record):
            with mock.patch('user.mqttpublish.time') as mock_time:
                mock_time.time.return_value = now

                final_record = SUT.update_record(topic_dict, now, record)

                self.assertEqual(final_record['interval_end_ts'], 1020)

                updated_record[field1] = updated_record[field1] + 100
                mock_time.time.return_value = 1010.0

                final_record = SUT.update_record(topic_dict, 1010.0, record)

                self.assertIn(field1, final_record)
                self.assertNotIn('interval_end_ts', final_record)

    def test_update_field(self):
        mock_logger_queue = mock.Mock()
        config_dict = {}
        config = configobj.ConfigObj(config_dict)
        config = {}
        topics_loop = {}
        topics_archive = {}
        data_queue_mock = mock.Mock()
        weewx_dict = {
            'config_dict': {
                'MQTTPublish': {}
            }
        }

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        SUT = user.mqttpublish.QueueProcessor(mock_logger_queue,
                                              {},
                                              weewx_dict,
                                              None,
                                              config,
                                              monitor_dict,
                                              topics_loop,
                                              topics_archive,
                                              data_queue_mock)

        field1 = helpers.random_string()

        topic_dict = {
            'unit_system': 1,
            'fields': {
                field1: {
                    'unit': 'foobar',
                    'append_unit_label': True,
                    'conversion_type': 'float',
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

                self.assertEqual(name, f"{field1}_{topic_dict['fields'][field1]['unit']}")
                self.assertEqual(value, converted_value)

    def test_update_record_all_fields_ignored(self):
        mock_logger_queue = mock.Mock()
        weewx_dict = {
            'config_dict': {
                'MQTTPublish': {}
            }
        }

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        SUT = user.mqttpublish.QueueProcessor(mock_logger_queue,
                                              {},
                                              weewx_dict,
                                              None,
                                              {},
                                              monitor_dict,
                                              {},
                                              {},
                                              None)

        field1 = helpers.random_string()
        now = 1000.0

        record = {
            'dateTime': now,
            'usUnits': 1,
        }

        updated_record = {
            field1: random.random(),
            'usUnits': 1,
        }

        for minimum_interval in (None, 60):
            topic_dict = {
                'unit_system': 1,
                'ignore': True,
                'fields': {},
                'minimum_interval': minimum_interval,
                'data_last_published': {},
            }

            with mock.patch.object(user.mqttpublish.weewx.units, 'to_std_system', return_value=updated_record):
                with mock.patch('user.mqttpublish.time') as mock_time:
                    mock_time.time.return_value = now

                    final_record = SUT.update_record(topic_dict, now, record)

            self.assertDictEqual(final_record, {})

    def test_update_record_all_fields_none(self):
        mock_logger_queue = mock.Mock()
        weewx_dict = {
            'config_dict': {
                'MQTTPublish': {}
            }
        }

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        SUT = user.mqttpublish.QueueProcessor(mock_logger_queue,
                                              {},
                                              weewx_dict,
                                              None,
                                              {},
                                              monitor_dict,
                                              {},
                                              {},
                                              None)

        field1 = helpers.random_string()
        now = 1000.0

        record = {
            'dateTime': now,
            'usUnits': 1,
        }

        updated_record = {
            field1: None,
            'usUnits': 1,
        }

        topic_dict = {
            'unit_system': 1,
            'fields': {
                field1: {
                    'ignore': False,
                },
                'usUnits': {
                    'ignore': True,
                },
            },
            'minimum_interval': 60,
            'data_last_published': {},
        }

        with mock.patch.object(user.mqttpublish.weewx.units, 'to_std_system', return_value=updated_record):
            with mock.patch('user.mqttpublish.time') as mock_time:
                mock_time.time.return_value = now

                final_record = SUT.update_record(topic_dict, now, record)

        self.assertDictEqual(final_record, {})

    def test_run_services_client_while_idle(self):
        mock_logger_queue = mock.Mock()
        weewx_dict = {
            'config_dict': {
                'MQTTPublish': {}
            }
        }

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        data_queue = queue.Queue()
        mqtt_config = {
            'wait_for_queue_element': 0.05,
        }

        SUT = user.mqttpublish.QueueProcessor(mock_logger_queue,
                                              {},
                                              weewx_dict,
                                              None,
                                              mqtt_config,
                                              monitor_dict,
                                              {},
                                              {},
                                              data_queue)

        mock_publisher = mock.Mock()

        run_thread = threading.Thread(target=SUT.run, daemon=True)
        with mock.patch.object(user.mqttpublish.AbstractPublisher, 'get_publisher', return_value=mock_publisher):
            with mock.patch('user.mqttpublish.weewx.manager'):
                run_thread.start()
                try:
                    time.sleep(0.5)

                    self.assertGreaterEqual(mock_publisher.client.loop.call_count, 1)
                finally:
                    data_queue.put({'time_stamp': time.time(), 'type': 'shutdown', 'data': {}})
                    run_thread.join(timeout=5)

        self.assertFalse(run_thread.is_alive())

if __name__ == '__main__':
    helpers.run_tests()

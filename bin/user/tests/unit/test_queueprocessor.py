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
import json
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
                                              data_queue,
                                              {'plugins': {},
                                               'weewx_dict': weewx_dict,
                                               'manager_dict': None,
                                               'mqtt_config': config,
                                               'monitor_config': monitor_dict,
                                               'topics_loop': topics_loop,
                                               'topics_archive': topics_archive})

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
                                              None,
                                              {'plugins': {},
                                               'weewx_dict': weewx_dict,
                                               'manager_dict': None,
                                               'mqtt_config': {},
                                               'monitor_config': monitor_dict,
                                               'topics_loop': {},
                                               'topics_archive': {}})

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
                                              data_queue_mock,
                                              {'plugins': {},
                                               'weewx_dict': weewx_dict,
                                               'manager_dict': None,
                                               'mqtt_config': config,
                                               'monitor_config': monitor_dict,
                                               'topics_loop': topics_loop,
                                               'topics_archive': topics_archive})

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
                                              None,
                                              {'plugins': {},
                                               'weewx_dict': weewx_dict,
                                               'manager_dict': None,
                                               'mqtt_config': {},
                                               'monitor_config': monitor_dict,
                                               'topics_loop': {},
                                               'topics_archive': {}})

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
                                              None,
                                              {'plugins': {},
                                               'weewx_dict': weewx_dict,
                                               'manager_dict': None,
                                               'mqtt_config': {},
                                               'monitor_config': monitor_dict,
                                               'topics_loop': {},
                                               'topics_archive': {}})

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

    def test_update_record_none_value_within_interval(self):
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
                                              None,
                                              {'plugins': {},
                                               'weewx_dict': weewx_dict,
                                               'manager_dict': None,
                                               'mqtt_config': {},
                                               'monitor_config': monitor_dict,
                                               'topics_loop': {},
                                               'topics_archive': {}})

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
                    'publish_none_value': True,
                },
                'usUnits': {
                    'ignore': True,
                },
            },
            'minimum_interval': 60,
            'suppression_threshold': 0.0,
            'data_last_published': {},
        }

        with mock.patch.object(user.mqttpublish.weewx.units, 'to_std_system', return_value=updated_record):
            with mock.patch('user.mqttpublish.time') as mock_time:
                mock_time.time.return_value = now

                # A new interval always publishes the None value.
                final_record = SUT.update_record(topic_dict, now, record)

                self.assertDictEqual(final_record, {field1: None, 'interval_end_ts': 1020})

                # The same None value within the interval is suppressed.
                final_record = SUT.update_record(topic_dict, now, record)

                self.assertDictEqual(final_record, {})

                # A transition to a value within the interval is published.
                updated_record[field1] = 5.567
                final_record = SUT.update_record(topic_dict, now, record)

                self.assertDictEqual(final_record, {field1: 5.567})

                # The same value within the interval is suppressed.
                final_record = SUT.update_record(topic_dict, now, record)

                self.assertDictEqual(final_record, {})

                # A transition back to None within the interval is published.
                updated_record[field1] = None
                final_record = SUT.update_record(topic_dict, now, record)

                self.assertDictEqual(final_record, {field1: None})

    def test_run_does_not_pump_client_loop_while_idle(self):
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
                                              data_queue,
                                              {'plugins': {},
                                               'weewx_dict': weewx_dict,
                                               'manager_dict': None,
                                               'mqtt_config': mqtt_config,
                                               'monitor_config': monitor_dict,
                                               'topics_loop': {},
                                               'topics_archive': {}})

        mock_publisher = mock.Mock()
        real_sleep = time.sleep

        run_thread = threading.Thread(target=SUT.run, daemon=True)
        with mock.patch.object(user.mqttpublish, 'Publisher', return_value=mock_publisher):
            with mock.patch('user.mqttpublish.weewx.manager'):
                with mock.patch('user.mqttpublish.time.sleep') as mock_sleep:
                    run_thread.start()
                    try:
                        real_sleep(0.5)

                        # paho's network loop thread services the client; the queue processor must not pump it.
                        mock_publisher.client.loop.assert_not_called()
                        mock_sleep.assert_not_called()
                    finally:
                        data_queue.put({'time_stamp': time.time(), 'type': 'shutdown', 'data': {}})
                        run_thread.join(timeout=5)

        self.assertFalse(run_thread.is_alive())

class TestUpdateField(unittest.TestCase):
    def test_unconfigured_field_passes_through(self):
        topic_dict = {}
        fieldinfo = {}
        field = helpers.random_string()
        value = 70.5

        name, converted = user.mqttpublish.QueueProcessor.update_field(topic_dict, fieldinfo, field, value, 1)

        self.assertEqual(name, field)
        self.assertEqual(converted, value)

    def test_name_override_is_used(self):
        topic_dict = {}
        fieldinfo = {'name': helpers.random_string()}
        field = helpers.random_string()
        value = 70.5

        name, _ = user.mqttpublish.QueueProcessor.update_field(topic_dict, fieldinfo, field, value, 1)

        self.assertEqual(name, fieldinfo['name'])

    def test_append_unit_label_resolves_standard_type_when_unit_is_absent(self):
        topic_dict = {}
        fieldinfo = {'append_unit_label': True}
        field = helpers.random_string()
        value = 70.5

        with mock.patch.object(user.mqttpublish.weewx.units,
                               'getStandardUnitType',
                               return_value=('degree_F', 'group_temperature')):
            name, converted = user.mqttpublish.QueueProcessor.update_field(topic_dict, fieldinfo, field, value, 1)

        # degree_F reduces to F, so the label carries the reduced form.
        self.assertEqual(name, f"{field}_F")
        self.assertEqual(converted, value)

    def test_append_unit_label_skipped_when_unit_type_reduces_to_none(self):
        topic_dict = {}
        fieldinfo = {'append_unit_label': True}
        field = helpers.random_string()
        value = 45.0

        with mock.patch.object(user.mqttpublish.weewx.units,
                               'getStandardUnitType',
                               return_value=('degree_compass', 'group_direction')):
            name, _ = user.mqttpublish.QueueProcessor.update_field(topic_dict, fieldinfo, field, value, 1)

        # degree_compass has no short label, so the name is left untouched.
        self.assertEqual(name, field)

    def test_integer_conversion_type_truncates_value(self):
        topic_dict = {}
        fieldinfo = {'conversion_type': 'integer'}
        field = helpers.random_string()
        value = 42.7

        _, converted = user.mqttpublish.QueueProcessor.update_field(topic_dict, fieldinfo, field, value, 1)

        self.assertEqual(converted, 42)

    def test_float_conversion_type_preserves_fraction(self):
        topic_dict = {}
        fieldinfo = {'conversion_type': 'float'}
        field = helpers.random_string()
        value = 42

        _, converted = user.mqttpublish.QueueProcessor.update_field(topic_dict, fieldinfo, field, value, 1)

        self.assertIsInstance(converted, float)
        self.assertEqual(converted, 42.0)

    def test_round_is_applied_to_float_value(self):
        topic_dict = {}
        fieldinfo = {'round': 2}
        field = helpers.random_string()
        value = 3.14159

        _, converted = user.mqttpublish.QueueProcessor.update_field(topic_dict, fieldinfo, field, value, 1)

        self.assertEqual(converted, 3.14)

    def test_round_leaves_non_float_value_alone(self):
        # The round setting only applies to floats; an integer is not re-rounded.
        topic_dict = {}
        fieldinfo = {'round': 2}
        field = helpers.random_string()
        value = 42

        _, converted = user.mqttpublish.QueueProcessor.update_field(topic_dict, fieldinfo, field, value, 1)

        self.assertEqual(converted, value)

    def test_topic_level_options_are_used_when_field_does_not_override(self):
        topic_dict = {'round': 1, 'conversion_type': 'float'}
        fieldinfo = {}
        field = helpers.random_string()
        value = 42

        name, converted = user.mqttpublish.QueueProcessor.update_field(topic_dict, fieldinfo, field, value, 1)

        self.assertEqual(name, field)
        self.assertEqual(converted, 42.0)

class TestPublishRecord(unittest.TestCase):
    @staticmethod
    def _make_processor():
        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        SUT = user.mqttpublish.QueueProcessor(mock.Mock(),
                                              None,
                                              {'plugins': {},
                                               'weewx_dict': {},
                                               'manager_dict': None,
                                               'mqtt_config': {},
                                               'monitor_config': monitor_dict,
                                               'topics_loop': {},
                                               'topics_archive': {}})
        SUT.publisher = mock.Mock()
        return SUT

    @staticmethod
    def _topic_dict(topic_type):
        return {
            'type': topic_type,
            'qos': random.randint(0, 2),
            'retain': random.choice([True, False]),
        }

    def test_publish_record_empty_record_is_not_published(self):
        SUT = self._make_processor()

        SUT.publish_record(time.time(), helpers.random_string(), self._topic_dict('json'), {})

        # pylint: disable=no-member
        SUT.publisher.publish_message.assert_not_called()

    def test_publish_record_json(self):
        SUT = self._make_processor()
        time_stamp = time.time()
        topic = helpers.random_string()
        topic_dict = self._topic_dict('json')
        updated_record = {
            helpers.random_string(): random.random(),
            helpers.random_string(): helpers.random_string(),
        }

        SUT.publish_record(time_stamp, topic, topic_dict, updated_record)

        SUT.publisher.publish_message.assert_called_once_with(time_stamp,
                                                              topic_dict['qos'],
                                                              topic_dict['retain'],
                                                              topic,
                                                              json.dumps(updated_record))

    def test_publish_record_keyword(self):
        SUT = self._make_processor()
        time_stamp = time.time()
        topic = helpers.random_string()
        topic_dict = self._topic_dict('keyword')
        updated_record = {
            helpers.random_string(): random.random(),
            helpers.random_string(): helpers.random_string(),
        }

        SUT.publish_record(time_stamp, topic, topic_dict, updated_record)

        expected_data = ', '.join(f"{key}={val}" for (key, val) in updated_record.items())
        SUT.publisher.publish_message.assert_called_once_with(time_stamp,
                                                              topic_dict['qos'],
                                                              topic_dict['retain'],
                                                              topic,
                                                              expected_data)

    def test_publish_record_individual(self):
        SUT = self._make_processor()
        time_stamp = time.time()
        topic = helpers.random_string()
        topic_dict = self._topic_dict('individual')
        updated_record = {
            helpers.random_string(): random.random(),
            helpers.random_string(): helpers.random_string(),
        }

        SUT.publish_record(time_stamp, topic, topic_dict, updated_record)

        self.assertEqual(SUT.publisher.publish_message.call_count, len(updated_record))
        for key, value in updated_record.items():
            SUT.publisher.publish_message.assert_any_call(time_stamp,
                                                          topic_dict['qos'],
                                                          topic_dict['retain'],
                                                          topic + '/' + key,
                                                          value)

class TestPublishRow(unittest.TestCase):
    @staticmethod
    def _make_processor():
        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        SUT = user.mqttpublish.QueueProcessor(mock.Mock(),
                                              None,
                                              {'plugins': {},
                                               'weewx_dict': {},
                                               'manager_dict': None,
                                               'mqtt_config': {},
                                               'monitor_config': monitor_dict,
                                               'topics_loop': {},
                                               'topics_archive': {}})
        SUT.publisher = mock.Mock()
        return SUT

    def test_publish_row(self):
        SUT = self._make_processor()

        mock_immediate_callback = mock.Mock()
        mock_delay_callback = mock.Mock()
        SUT.publisher.plugin_manager.callbacks = {
            'update_record': {
                'immediate': {helpers.random_string(): mock_immediate_callback},
                'delay': {helpers.random_string(): mock_delay_callback},
            },
        }

        qos = random.randint(0, 2)
        retain = random.choice([True, False])
        unit_system = random.randint(0, 2)
        topics = {
            helpers.random_string(): {'qos': qos, 'retain': retain, 'unit_system': unit_system},
            helpers.random_string(): {'qos': qos, 'retain': retain, 'unit_system': unit_system},
        }

        data = {'usUnits': random.randint(1, 3), helpers.random_string(): random.random()}

        updated_record = {helpers.random_string(): helpers.random_string()}
        SUT.update_record = mock.Mock(return_value=updated_record)
        SUT.publish_record = mock.Mock()

        time_stamp = time.time()
        SUT.publish_row(time_stamp, data, topics)

        # The immediate callbacks run once per topic with a deep copy of the data.
        self.assertEqual(mock_immediate_callback.call_count, len(topics))
        for call in mock_immediate_callback.call_args_list:
            args = call[0]
            self.assertIs(args[0], SUT.publisher.client)
            self.assertEqual(args[3], data['usUnits'])
            self.assertEqual(args[4], qos)
            self.assertEqual(args[5], retain)
            # A copy, not the original object, so a plugin cannot mutate the source data.
            self.assertIsNot(args[2], data)
            self.assertDictEqual(args[2], data)
        self.assertEqual({call[0][1] for call in mock_immediate_callback.call_args_list}, set(topics))

        # update_record runs once per topic.
        self.assertEqual(SUT.update_record.call_count, len(topics))

        # The delay callbacks run once per topic against the update_record output.
        self.assertEqual(mock_delay_callback.call_count, len(topics))
        for call in mock_delay_callback.call_args_list:
            args = call[0]
            self.assertIs(args[0], SUT.publisher.client)
            self.assertIs(args[2], updated_record)
            self.assertEqual(args[3], unit_system)
            self.assertEqual(args[4], qos)
            self.assertEqual(args[5], retain)
        self.assertEqual({call[0][1] for call in mock_delay_callback.call_args_list}, set(topics))

        # publish_record runs once per topic with the updated record.
        self.assertEqual(SUT.publish_record.call_count, len(topics))
        for call in SUT.publish_record.call_args_list:
            args = call[0]
            self.assertEqual(args[0], time_stamp)
            self.assertIs(args[2], topics[args[1]])
            self.assertIs(args[3], updated_record)
        self.assertEqual({call[0][1] for call in SUT.publish_record.call_args_list}, set(topics))

    def test_publish_row_immediate_callback_receives_same_record_as_update_record(self):
        SUT = self._make_processor()

        mock_immediate_callback = mock.Mock()
        SUT.publisher.plugin_manager.callbacks = {
            'update_record': {
                'immediate': {helpers.random_string(): mock_immediate_callback},
                'delay': {},
            },
        }

        topic1 = helpers.random_string()
        topics = {
            topic1: {'qos': 0, 'retain': False, 'unit_system': 1},
        }
        data = {'usUnits': 1, 'outTemp': 70.0}

        SUT.update_record = mock.Mock(return_value={})
        SUT.publish_record = mock.Mock()

        SUT.publish_row(time.time(), data, topics)

        # The record handed to the immediate plugins is the same object passed to update_record.
        immediate_record = mock_immediate_callback.call_args[0][2]
        update_record_arg = SUT.update_record.call_args[0][2]
        self.assertIs(immediate_record, update_record_arg)

class TestHandleQueueItem(unittest.TestCase):
    @staticmethod
    def _make_processor(topics_loop=None, topics_archive=None):
        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        data_queue = mock.Mock()
        data_queue.qsize.return_value = 0

        SUT = user.mqttpublish.QueueProcessor(mock.Mock(),
                                              data_queue,
                                              {'plugins': {},
                                               'weewx_dict': {},
                                               'manager_dict': None,
                                               'mqtt_config': {},
                                               'monitor_config': monitor_dict,
                                               'topics_loop': topics_loop or {},
                                               'topics_archive': topics_archive or {}})
        SUT.publisher = mock.Mock()
        return SUT

    @staticmethod
    def _topic_dict():
        return {'qos': 0, 'retain': False, 'unit_system': 1}

    @staticmethod
    def _instrument(SUT):
        """ Replace the collaborating methods with recorders that note call order.

        Returns (order, immediate, publish, delay); assert on the returned mocks
        rather than on SUT attributes so the test's intent is explicit.
        """
        order = []
        immediate = mock.Mock(side_effect=lambda _data2: order.append('immediate'))
        publish = mock.Mock(side_effect=lambda *_args: order.append('publish'))
        delay = mock.Mock(side_effect=lambda _data2: order.append('delay'))
        SUT.on_weewx_data_immediate = immediate
        SUT.publish_row = publish
        SUT.on_weewx_data_delay = delay
        return order, immediate, publish, delay

    def test_shutdown_item_stops_processor(self):
        SUT = self._make_processor()
        order, immediate, publish, _delay = self._instrument(SUT)

        result = SUT.handle_queue_item({'type': 'shutdown'}, time.time())

        # The processor stops and nothing is published for a shutdown item.
        self.assertIsNone(result)
        self.assertFalse(SUT.process)
        self.assertEqual(order, [])
        immediate.assert_not_called()
        publish.assert_not_called()
        log_messages = [call[0][0]['msg_text'] for call in SUT.logger_queue.put.call_args_list]
        self.assertIn("Shutting down queue processor.", log_messages)

    def test_loop_item_publishes_to_loop_topics(self):
        loop_topics = {helpers.random_string(): self._topic_dict()}
        archive_topics = {helpers.random_string(): self._topic_dict()}
        SUT = self._make_processor(topics_loop=loop_topics, topics_archive=archive_topics)
        order, immediate, publish, delay = self._instrument(SUT)

        data2 = {'type': 'loop', 'time_stamp': time.time(), 'data': {'usUnits': 1}}
        prev_time = time.time() - 1
        result = SUT.handle_queue_item(data2, prev_time)

        # The queue size is recorded on the item handed to the plugins.
        self.assertEqual(data2['queue_size'], 0)
        publish.assert_called_once_with(data2['time_stamp'], data2['data'], loop_topics)
        # Immediate plugins run first, then publishing, then the delay plugins.
        self.assertEqual(order, ['immediate', 'publish', 'delay'])
        immediate.assert_called_once_with(data2)
        delay.assert_called_once_with(data2)
        # The returned time advances so the next queue item logs an accurate duration.
        self.assertGreaterEqual(result, prev_time)

    def test_archive_item_publishes_to_archive_topics(self):
        loop_topics = {helpers.random_string(): self._topic_dict()}
        archive_topics = {helpers.random_string(): self._topic_dict()}
        SUT = self._make_processor(topics_loop=loop_topics, topics_archive=archive_topics)
        order, _immediate, publish, _delay = self._instrument(SUT)

        data2 = {'type': 'archive', 'time_stamp': time.time(), 'data': {'usUnits': 1}}
        SUT.handle_queue_item(data2, time.time())

        publish.assert_called_once_with(data2['time_stamp'], data2['data'], archive_topics)
        self.assertEqual(order, ['immediate', 'publish', 'delay'])

    def test_unknown_type_publishes_nothing_and_logs_error(self):
        loop_topics = {helpers.random_string(): self._topic_dict()}
        archive_topics = {helpers.random_string(): self._topic_dict()}
        SUT = self._make_processor(topics_loop=loop_topics, topics_archive=archive_topics)
        order, _immediate, publish, _delay = self._instrument(SUT)

        data2 = {'type': 'bogus', 'time_stamp': time.time(), 'data': {'usUnits': 1}}
        result = SUT.handle_queue_item(data2, time.time())

        # Nothing is published, but the plugins still run and the time advances.
        publish.assert_not_called()
        self.assertEqual(order, ['immediate', 'delay'])
        self.assertIsNotNone(result)
        log_messages = [call[0][0]['msg_text'] for call in SUT.logger_queue.put.call_args_list]
        self.assertIn("Unknown data type, bogus", log_messages)


class TestOnWeewxData(unittest.TestCase):
    @staticmethod
    def _make_processor():
        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': 'MONITOR',
        }

        SUT = user.mqttpublish.QueueProcessor(mock.Mock(),
                                              None,
                                              {'plugins': {},
                                               'weewx_dict': {},
                                               'manager_dict': None,
                                               'mqtt_config': {},
                                               'monitor_config': monitor_dict,
                                               'topics_loop': {},
                                               'topics_archive': {}})
        SUT.publisher = mock.Mock()
        # Drop the "Initializing queue processor." entry logged by __init__ so the
        # assertions below see only what the method under test emits.
        SUT.logger_queue.reset_mock()
        # The on_weewx_data callbacks hang off the processor's own plugin manager.
        SUT.plugin_manager = mock.Mock()
        SUT.plugin_manager.callbacks = {
            'on_weewx_data': {'immediate': {}, 'delay': {}},
        }
        return SUT

    @staticmethod
    def _log_messages(SUT):
        return [call[0][0] for call in SUT.logger_queue.put.call_args_list]

    @staticmethod
    def _register(SUT, timing, calls, names):
        """ Register one mock plugin per name; each records its own name in calls. """
        registered = {}
        for name in names:
            registered[name] = mock.Mock(side_effect=lambda _data2, _name=name: calls.append(_name))
        SUT.plugin_manager.callbacks['on_weewx_data'][timing] = registered
        return registered

    def test_immediate_runs_plugins_in_order_and_logs_timings(self):
        SUT = self._make_processor()
        calls = []
        plugin_a, plugin_b = helpers.random_string(), helpers.random_string()
        registered = self._register(SUT, 'immediate', calls, [plugin_a, plugin_b])

        data2 = {'type': 'loop', helpers.random_string(): helpers.random_string()}
        SUT.on_weewx_data_immediate(data2)

        # Every plugin sees the queue item, in registration order.
        self.assertEqual(calls, [plugin_a, plugin_b])
        registered[plugin_a].assert_called_once_with(data2)
        registered[plugin_b].assert_called_once_with(data2)

        # One timing line per plugin plus a summary line, all under the monitor flag.
        messages = self._log_messages(SUT)
        self.assertEqual(len(messages), 3)
        for message in messages:
            self.assertEqual(message['log_type'], 'MONITOR')
        self.assertIn(plugin_a, messages[0]['msg_text'])
        self.assertIn("on_weewx_data (immediate)", messages[0]['msg_text'])
        self.assertIn(plugin_b, messages[1]['msg_text'])
        # The summary reports the total, so it names no individual plugin.
        self.assertIn("on_weewx_data (immediate)", messages[2]['msg_text'])
        self.assertNotIn(plugin_a, messages[2]['msg_text'])
        self.assertNotIn(plugin_b, messages[2]['msg_text'])

    def test_immediate_with_no_plugins_still_logs_summary(self):
        SUT = self._make_processor()

        SUT.on_weewx_data_immediate({'type': 'loop'})

        messages = self._log_messages(SUT)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['log_type'], 'MONITOR')
        self.assertIn("on_weewx_data (immediate)", messages[0]['msg_text'])

    def test_delay_runs_plugins_in_order_and_logs_timings(self):
        SUT = self._make_processor()
        calls = []
        plugin_a, plugin_b = helpers.random_string(), helpers.random_string()
        registered = self._register(SUT, 'delay', calls, [plugin_a, plugin_b])

        data2 = {'type': 'archive', helpers.random_string(): helpers.random_string()}
        SUT.on_weewx_data_delay(data2)

        self.assertEqual(calls, [plugin_a, plugin_b])
        registered[plugin_a].assert_called_once_with(data2)
        registered[plugin_b].assert_called_once_with(data2)

        messages = self._log_messages(SUT)
        self.assertEqual(len(messages), 3)
        for message in messages:
            self.assertEqual(message['log_type'], 'MONITOR')
        self.assertIn(plugin_a, messages[0]['msg_text'])
        self.assertIn("on_weewx_data (delay)", messages[0]['msg_text'])
        self.assertIn(plugin_b, messages[1]['msg_text'])
        self.assertIn("on_weewx_data (delay)", messages[2]['msg_text'])
        self.assertNotIn(plugin_a, messages[2]['msg_text'])
        self.assertNotIn(plugin_b, messages[2]['msg_text'])

    def test_delay_with_no_plugins_still_logs_summary(self):
        SUT = self._make_processor()

        SUT.on_weewx_data_delay({'type': 'archive'})

        messages = self._log_messages(SUT)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['log_type'], 'MONITOR')
        self.assertIn("on_weewx_data (delay)", messages[0]['msg_text'])


class TestPublishWeeWXProcess(unittest.TestCase):
    def test_run_logs_error_when_processor_does_not_shutdown(self):
        mock_logger_queue = mock.Mock()

        monitor_dict = {
            'monitor_queue': None,
            'monitor_on_message': None,
            'monitor_on_connect': None,
            'monitor_record_update': None,
            'monitor_on_weewx_data': None,
        }

        data_queue = queue.Queue()
        data_queue.put({'time_stamp': time.time(), 'type': 'shutdown', 'data': {}})

        with mock.patch('user.mqttpublish.QueueProcessor'):
            SUT = user.mqttpublish.PublishWeeWXProcess(mock_logger_queue,
                                                       data_queue,
                                                       {'plugins': {},
                                                        'weewx_dict': {},
                                                        'manager_dict': None,
                                                        'mqtt_config': {},
                                                        'monitor_config': monitor_dict,
                                                        'topics_loop': {},
                                                        'topics_archive': {}})

        processor_name = helpers.random_string()
        SUT.processor.name = processor_name
        SUT.processor.is_alive.return_value = True

        SUT.run()

        SUT.processor.join.assert_called_once_with(5)
        mock_logger_queue.put.assert_any_call(
            user.mqttpublish.Logger.create_entry(SUT.name, 'ERROR', 0, f"Unable to shut down {processor_name}"))

if __name__ == '__main__':
    helpers.run_tests()

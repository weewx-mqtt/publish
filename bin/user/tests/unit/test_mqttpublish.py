#    Copyright (c) 2025-2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name

import configobj
import contextlib
import queue as Queue
import time

import unittest
import mock

import weewx

import helpers
import user.mqttpublish

class TestInit(unittest.TestCase):
    def test_PublishWeeWX_stanza_is_deprecated(self):
        mock_engine = mock.Mock()
        config_dict = {
            'StdReport': {},
            'MQTTPublish': {
                'PublishWeeWX': {
                    'topics': {}
                }
            }
        }
        config = configobj.ConfigObj(config_dict)

        # with mock.patch('user.mqttpublish.mqtt'):
        with mock.patch('user.mqttpublish.weewx.manager'):
            with mock.patch('user.mqttpublish.PublishWeeWXThread'):
                with mock.patch('user.mqttpublish.Logger'):
                    SUT = user.mqttpublish.MQTTPublish(mock_engine, config)
                    SUT.logger_queue.put(None)
                    self.assertEqual(SUT.logger.logerr.call_count, 1)
                    #SUT.logger.logerr.assert_called_once_with("",
                    #                                        "'PublishWeeWX' is deprecated. Move options to top level, '[MQTTPublish]'.")

    def test_log_mqtt_option(self):
        mock_engine = mock.Mock()
        config_dict = {
            'MQTTPublish': {
                'log_mqtt': True,
                'topics': {},
            }
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.weewx.manager'):
            with mock.patch('user.mqttpublish.PublishWeeWXThread'):
                with mock.patch('user.mqttpublish.Logger'):
                    SUT = user.mqttpublish.MQTTPublish(mock_engine, config)

        self.assertTrue(SUT.mqtt_config['log_mqtt'])

    @staticmethod
    def _build_service(config_dict):
        """ Construct an enabled MQTTPublish service with its collaborators mocked. """
        engine = mock.Mock()
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.weewx.manager'):
            with mock.patch('user.mqttpublish.PublishWeeWXThread'):
                with mock.patch('user.mqttpublish.PublishWeeWXProcess') as mock_process:
                    with mock.patch('user.mqttpublish.Logger') as mock_logger:
                        SUT = user.mqttpublish.MQTTPublish(engine, config)

        return SUT, engine, mock_logger.return_value, mock_process

    def test_deprecated_binding_option(self):
        SUT, _, mock_logger, _ = self._build_service({
            'MQTTPublish': {
                'binding': 'archive',
                'topics': {},
            }
        })

        mock_logger.loginf.assert_any_call(SUT.name, "'binding' is deprecated and no longer used.")

    def test_multiprocess_uses_process_thread(self):
        SUT, _, _, mock_process = self._build_service({
            'MQTTPublish': {
                'multiprocess': True,
                'topics': {},
            }
        })

        mock_process.assert_called_once()
        # pylint: disable=protected-access
        self.assertIs(SUT._thread, mock_process.return_value)

    def test_binds_archive_and_loop_events(self):
        _, engine, _, _ = self._build_service({
            'MQTTPublish': {
                'topics': {
                    helpers.random_string(): {},
                },
            }
        })

        bindings = [call[0][0] for call in engine.bind.call_args_list]
        self.assertIn(weewx.NEW_ARCHIVE_RECORD, bindings)
        self.assertIn(weewx.NEW_LOOP_PACKET, bindings)

    def test_report_defaults_are_merged(self):
        SUT, _, _, _ = self._build_service({
            'MQTTPublish': {
                'topics': {},
            },
            'StdReport': {
                'Defaults': {
                    'Station': {
                        'altitude': '111, foot',
                    },
                },
            },
        })

        self.assertEqual(SUT.weewx_dict['defaults']['Station']['altitude'], '111, foot')

    def test_deprecated_lwt_option(self):
        SUT, _, mock_logger, _ = self._build_service({
            'MQTTPublish': {
                'lwt': {
                    'topic': 'status',
                },
                'topics': {},
            }
        })

        mock_logger.logerr.assert_any_call(SUT.name,
                                           "'[[lwt]]' is deprecated.  use [[availability_topic]].")

class TestConfigurePlugins(unittest.TestCase):
    @staticmethod
    def _build_service(config_dict):
        """ Construct an MQTTPublish service and return it with its mock logger. """
        with mock.patch('user.mqttpublish.Logger') as mock_logger:
            SUT = user.mqttpublish.MQTTPublish(mock.Mock(), configobj.ConfigObj(config_dict))

        return SUT, mock_logger.return_value

    def test_plugins_stanza_is_deprecated(self):
        SUT, mock_logger = self._build_service({
            'MQTTPublish': {
                'enable': False,
                'plugins': {
                    'PluginA': {'key': 'value'},
                },
            },
        })

        mock_logger.logerr.assert_any_call(
            SUT.name,
            "'[[plugins]]' is deprecated. To configure see, https://weewx-mqtt.github.io/publish/plugins/")
        self.assertIn('PluginA', SUT.plugins)

    def test_plugins_list_reports_missing_configuration(self):
        SUT, mock_logger = self._build_service({
            'MQTTPublish': {
                'enable': False,
                'plugins': ['PluginA', 'PluginB'],
            },
            'PluginA': {'key': 'value'},
        })

        self.assertIn('PluginA', SUT.plugins)
        self.assertNotIn('PluginB', SUT.plugins)
        mock_logger.logerr.assert_any_call(SUT.name, 'PluginB is missing its configuration section.')

class TestConfigureTopics(unittest.TestCase):
    def test_config_topics(self):
        mock_engine = mock.Mock()
        config_dict = {
            'MQTTPublish': {
                'enable': False,
            }
        }
        config = configobj.ConfigObj(config_dict)

        topic1 = helpers.random_string()
        service_dict = {
            'topics': {
                topic1: {},
            },
        }
        service_config = configobj.ConfigObj(service_dict)

        with mock.patch('user.mqttpublish.PublishWeeWXThread'):
            with mock.patch('user.mqttpublish.Logger'):
                SUT = user.mqttpublish.MQTTPublish(mock_engine, config)

                topics_loop, topics_archive, _ = SUT.configure_topics(service_config)

                expected_topics = {
                    topic1: {
                        'qos': 0,
                        'minimum_interval': 0,
                        'suppression_threshold': 0.0,
                        'retain': False,
                        'type': 'json',
                        'unit_system': 1,
                        'ignore': False,
                        'append_unit_label': True,
                        'conversion_type': 'string',
                        'round': None,
                        'format_string': None,
                        'fields': {},
                        'data_last_published': {},
                    }
                }

                self.assertDictEqual(topics_loop, expected_topics)
                self.assertDictEqual(topics_archive, expected_topics)

    def test_config_topics_with_fields(self):
        mock_engine = mock.Mock()
        config_dict = {
            'MQTTPublish': {
                'enable': False,
            }
        }
        config = configobj.ConfigObj(config_dict)

        topic1 = helpers.random_string()
        field1 = helpers.random_string()
        service_dict = {
            'topics': {
                topic1: {
                    'fields': {
                        field1: {},
                    },
                },
            },
        }
        service_config = configobj.ConfigObj(service_dict)

        with mock.patch('user.mqttpublish.PublishWeeWXThread'):
            with mock.patch('user.mqttpublish.Logger'):
                SUT = user.mqttpublish.MQTTPublish(mock_engine, config)

                topics_loop, topics_archive, _ = SUT.configure_topics(service_config)

                expected_topics = {
                    topic1: {
                        'qos': 0,
                        'minimum_interval': 0,
                        'suppression_threshold': 0.0,
                        'retain': False,
                        'type': 'json',
                        'unit_system': 1,
                        'ignore': False,
                        'append_unit_label': True,
                        'conversion_type': 'string',
                        'round': None,
                        'format_string': None,
                        'data_last_published': {},
                        'fields': {
                            field1: {
                                'name': field1,
                                'unit': None,
                                'ignore': False,
                                'publish_none_value': False,
                                'append_unit_label': True,
                                'conversion_type': 'string',
                                'round': None,
                                'format_string': None
                            }
                        }
                    }
                }

                self.assertDictEqual(topics_loop, expected_topics)
                self.assertDictEqual(topics_archive, expected_topics)

    def test_config_topics_with_field_defaults(self):
        mock_engine = mock.Mock()
        config_dict = {
            'MQTTPublish': {
                'enable': False,
            }
        }
        config = configobj.ConfigObj(config_dict)

        topic1 = helpers.random_string()
        field1 = helpers.random_string()
        field2 = helpers.random_string()
        service_dict = {
            'topics': {
                topic1: {
                    'ignore': True,
                    'publish_none_value': True,
                    'append_unit_label': False,
                    'conversion_type': 'float',
                    'round': 2,
                    'format_string': '%s',
                    'fields': {
                        field1: {
                            'ignore': False,
                        },
                        field2: {
                            'round': 0,
                        },
                    },
                },
            },
        }
        service_config = configobj.ConfigObj(service_dict)

        with mock.patch('user.mqttpublish.PublishWeeWXThread'):
            with mock.patch('user.mqttpublish.Logger'):
                SUT = user.mqttpublish.MQTTPublish(mock_engine, config)

                topics_loop, topics_archive, _ = SUT.configure_topics(service_config)

                expected_fields = {
                    field1: {
                        'name': field1,
                        'unit': None,
                        'ignore': False,
                        'publish_none_value': True,
                        'append_unit_label': False,
                        'conversion_type': 'float',
                        'round': 2,
                        'format_string': '%s'
                    },
                    field2: {
                        'name': field2,
                        'unit': None,
                        'ignore': True,
                        'publish_none_value': True,
                        'append_unit_label': False,
                        'conversion_type': 'float',
                        'round': 0,
                        'format_string': '%s'
                    }
                }

                self.assertDictEqual(topics_loop[topic1]['fields'], expected_fields)
                self.assertDictEqual(topics_archive[topic1]['fields'], expected_fields)

    def test_config_topics_requires_topics_stanza(self):
        mock_engine = mock.Mock()
        config = configobj.ConfigObj({'MQTTPublish': {'enable': False}})

        service_config = configobj.ConfigObj({})

        with mock.patch('user.mqttpublish.PublishWeeWXThread'):
            with mock.patch('user.mqttpublish.Logger'):
                SUT = user.mqttpublish.MQTTPublish(mock_engine, config)

                with self.assertRaises(ValueError) as context:
                    SUT.configure_topics(service_config)

        self.assertEqual(str(context.exception), "[[topics]] is required.")

    def test_config_topics_not_published(self):
        mock_engine = mock.Mock()
        config = configobj.ConfigObj({'MQTTPublish': {'enable': False}})

        topic1 = helpers.random_string()
        service_dict = {
            'topics': {
                topic1: {
                    'publish': False,
                },
            },
        }
        service_config = configobj.ConfigObj(service_dict)

        with mock.patch('user.mqttpublish.PublishWeeWXThread'):
            with mock.patch('user.mqttpublish.Logger'):
                SUT = user.mqttpublish.MQTTPublish(mock_engine, config)

                topics_loop, topics_archive, binding = SUT.configure_topics(service_config)

        self.assertDictEqual(topics_loop, {})
        self.assertDictEqual(topics_archive, {})
        self.assertEqual(list(binding), [])

    def test_config_topics_binding_excludes_archive(self):
        mock_engine = mock.Mock()
        config = configobj.ConfigObj({'MQTTPublish': {'enable': False}})

        topic1 = helpers.random_string()
        service_dict = {
            'topics': {
                topic1: {
                    'binding': 'loop',
                },
            },
        }
        service_config = configobj.ConfigObj(service_dict)

        with mock.patch('user.mqttpublish.PublishWeeWXThread'):
            with mock.patch('user.mqttpublish.Logger'):
                SUT = user.mqttpublish.MQTTPublish(mock_engine, config)

                topics_loop, topics_archive, binding = SUT.configure_topics(service_config)

        self.assertIn(topic1, topics_loop)
        self.assertNotIn(topic1, topics_archive)
        self.assertEqual(list(binding), ['loop'])

    def test_config_topics_binding_excludes_loop(self):
        mock_engine = mock.Mock()
        config = configobj.ConfigObj({'MQTTPublish': {'enable': False}})

        topic1 = helpers.random_string()
        service_dict = {
            'topics': {
                topic1: {
                    'binding': 'archive',
                },
            },
        }
        service_config = configobj.ConfigObj(service_dict)

        with mock.patch('user.mqttpublish.PublishWeeWXThread'):
            with mock.patch('user.mqttpublish.Logger'):
                SUT = user.mqttpublish.MQTTPublish(mock_engine, config)

                topics_loop, topics_archive, binding = SUT.configure_topics(service_config)

        self.assertNotIn(topic1, topics_loop)
        self.assertIn(topic1, topics_archive)
        self.assertEqual(list(binding), ['archive'])

    def test_config_topics_with_field_list_overrides(self):
        mock_engine = mock.Mock()
        config = configobj.ConfigObj({'MQTTPublish': {'enable': False}})

        topic1 = helpers.random_string()
        ignore_field = helpers.random_string()
        publish_field = helpers.random_string()
        service_dict = {
            'topics': {
                topic1: {
                    'ignore_fields': ignore_field,
                    'publish_fields': publish_field,
                },
            },
        }
        service_config = configobj.ConfigObj(service_dict)

        with mock.patch('user.mqttpublish.PublishWeeWXThread'):
            with mock.patch('user.mqttpublish.Logger'):
                SUT = user.mqttpublish.MQTTPublish(mock_engine, config)

                topics_loop, _, _ = SUT.configure_topics(service_config)

        expected_fields = {
            ignore_field: {'ignore': True},
            publish_field: {'ignore': False},
        }
        self.assertDictEqual(topics_loop[topic1]['fields'], expected_fields)

    def test_config_topics_with_deprecated_aggregates(self):
        mock_engine = mock.Mock()
        config = configobj.ConfigObj({'MQTTPublish': {'enable': False}})

        topic1 = helpers.random_string()
        aggregate1 = helpers.random_string()
        observation1 = helpers.random_string()
        service_dict = {
            'topics': {
                topic1: {
                    'aggregates': {
                        aggregate1: {
                            'observation': observation1,
                            'aggregation': 'avg',
                        },
                    },
                },
            },
        }
        service_config = configobj.ConfigObj(service_dict)

        with mock.patch('user.mqttpublish.PublishWeeWXThread'):
            with mock.patch('user.mqttpublish.Logger'):
                SUT = user.mqttpublish.MQTTPublish(mock_engine, config)

                SUT.configure_topics(service_config)

        # pylint: disable=no-member
        self.assertEqual(SUT.logger.logerr.call_count, 1)
        self.assertEqual(SUT.plugins['MQTTAggregateValues']['module'], 'user.mqttaggregatevalues')
        self.assertEqual(SUT.plugins['MQTTAggregateValues']['topics'][topic1][aggregate1]['observation'],
                         observation1)
        self.assertEqual(SUT.plugins['MQTTAggregateValues']['topics'][topic1][aggregate1]['aggregation'], 'avg')

class ServiceBase(unittest.TestCase):
    """ Common fixture: an enabled MQTTPublish service with its collaborators mocked. """
    # Subclasses exercise protected members, hence the blanket disable.
    # pylint: disable=protected-access

    @contextlib.contextmanager
    def _service(self, **kwargs):
        """ Yield the service, the thread/process/logger mocks, and the logger. """
        engine = mock.Mock()
        config = configobj.ConfigObj(self._service_config(**kwargs))

        with mock.patch('user.mqttpublish.weewx.manager'):
            with mock.patch('user.mqttpublish.PublishWeeWXThread') as mock_thread:
                with mock.patch('user.mqttpublish.PublishWeeWXProcess') as mock_process:
                    with mock.patch('user.mqttpublish.Logger') as mock_logger:
                        SUT = user.mqttpublish.MQTTPublish(engine, config)
                        yield SUT, mock_thread, mock_process, mock_logger.return_value

    @staticmethod
    def _service_config(**kwargs):
        service_dict = {'topics': {}}
        service_dict.update(kwargs)
        return {'MQTTPublish': service_dict}

    @staticmethod
    def _kill_thread(SUT, replacement):
        """ Report the current publishing thread as dead; the next start yields replacement. """
        SUT._thread.is_alive.return_value = False
        replacement.is_alive.return_value = True
        return replacement

class TestHandleRecord(ServiceBase):
    # pylint: disable=protected-access
    # The patches have to stay in force while the service is exercised. Exiting
    # mock.patch restores the real PublishWeeWXThread, and the restart branch would
    # then build - and start - a genuine thread.

    def test_alive_thread_queues_record_and_logs_queue_size(self):
        with self._service(monitor_queue='MONITOR') as (SUT, _, _, _):
            data = {'dateTime': 1234567890, 'outTemp': 70.0}
            SUT._handle_record('loop', data)

            self.assertEqual(SUT.data_queue.qsize(), 1)
            item = SUT.data_queue.get_nowait()
            self.assertEqual(item, {'time_stamp': 1234567890, 'type': 'loop', 'data': data})
            log_item = SUT.logger_queue.get_nowait()
            self.assertEqual(log_item['log_type'], 'MONITOR')
            self.assertIn("Input queue size: 1", log_item['log_message'])
            # A live thread is not restarted.
            self.assertEqual(SUT.thread_restarts, 0)

    def test_alive_thread_record_without_dateTime_stamps_itself(self):
        with self._service() as (SUT, _, _, _):
            before = time.time()
            SUT._handle_record('archive', {'outTemp': 70.0})
            after = time.time()

            item = SUT.data_queue.get_nowait()
            self.assertGreaterEqual(item['time_stamp'], before)
            self.assertLessEqual(item['time_stamp'], after)

    def test_connected_publisher_resets_restart_count(self):
        with self._service() as (SUT, _, _, _):
            SUT.thread_restarts = 2
            SUT._thread.processor.publisher.connected = True

            SUT._handle_record('loop', {'dateTime': 1234567890})

            self.assertEqual(SUT.thread_restarts, 0)

    def test_unconnected_publisher_keeps_restart_count(self):
        with self._service() as (SUT, _, _, _):
            SUT.thread_restarts = 2
            SUT._thread.processor.publisher.connected = False

            SUT._handle_record('loop', {'dateTime': 1234567890})

            self.assertEqual(SUT.thread_restarts, 2)

    def test_absent_publisher_keeps_restart_count(self):
        with self._service() as (SUT, _, _, _):
            SUT.thread_restarts = 2
            SUT._thread.processor.publisher = None

            SUT._handle_record('loop', {'dateTime': 1234567890})

            self.assertEqual(SUT.thread_restarts, 2)

    def test_dead_thread_is_restarted_and_record_queued(self):
        with self._service(monitor_queue='MONITOR') as (SUT, mock_thread, _, _):
            dead_thread = SUT._thread
            replacement = self._kill_thread(SUT, mock.Mock())
            mock_thread.side_effect = lambda *_args: replacement
            builds_before = mock_thread.call_count
            starts_before = dead_thread.start.call_count

            data = {'dateTime': 1234567890, 'outTemp': 70.0}
            SUT._handle_record('loop', data)

            # A replacement publishing thread is built, marked a daemon, and started.
            self.assertEqual(mock_thread.call_count, builds_before + 1)
            self.assertIs(SUT._thread, replacement)
            self.assertTrue(replacement.daemon)
            self.assertEqual(replacement.start.call_count, 1)
            # The restart is counted, and the record is still queued.
            self.assertEqual(SUT.thread_restarts, 1)
            self.assertEqual(SUT.data_queue.get_nowait(),
                             {'time_stamp': 1234567890, 'type': 'loop', 'data': data})
            # The dead thread is not the one that got started by this call.
            self.assertEqual(dead_thread.start.call_count, starts_before)

    def test_dead_thread_restarted_with_process_when_multiprocess(self):
        with self._service(multiprocess=True) as (SUT, _, mock_process, _):
            replacement = self._kill_thread(SUT, mock.Mock())
            mock_process.side_effect = lambda *_args: replacement
            builds_before = mock_process.call_count

            SUT._handle_record('archive', {'dateTime': 1234567890})

            self.assertEqual(mock_process.call_count, builds_before + 1)
            self.assertIs(SUT._thread, replacement)
            self.assertEqual(SUT.thread_restarts, 1)

    def test_exhausted_restarts_raise_stop_now(self):
        with self._service() as (SUT, mock_thread, _, _):
            self._kill_thread(SUT, mock.Mock())
            builds_before = mock_thread.call_count
            SUT.thread_restarts = SUT.max_thread_restarts

            with self.assertRaises(weewx.StopNow):
                SUT._handle_record('loop', {'dateTime': 1234567890})

            # No replacement is built, nothing is queued, and the count is left as it was.
            self.assertEqual(mock_thread.call_count, builds_before)
            self.assertEqual(SUT.data_queue.qsize(), 0)
            self.assertEqual(SUT.thread_restarts, SUT.max_thread_restarts)

    def test_restart_path_requires_dateTime_while_live_path_defaults_it(self):
        with self._service() as (SUT, mock_thread, _, _):
            replacement = self._kill_thread(SUT, mock.Mock())
            mock_thread.side_effect = lambda *_args: replacement

            # The restarted-thread branch indexes the time stamp, so this raises.
            with self.assertRaises(KeyError):
                SUT._handle_record('loop', {'outTemp': 70.0})

            # With the thread alive the same record is accepted.
            SUT._thread = mock.Mock()
            SUT._thread.is_alive.return_value = True
            SUT._handle_record('loop', {'outTemp': 70.0})
            self.assertEqual(SUT.data_queue.qsize(), 1)

    def test_queue_backlog_is_logged_at_multiples_of_ten(self):
        with self._service() as (SUT, _, _, mock_logger):
            SUT._thread.is_alive.return_value = True
            for _ in range(9):
                SUT.data_queue.put({'dateTime': 1234567890})

            SUT._handle_record('loop', {'dateTime': 1234567890})
            mock_logger.logerr.assert_not_called()

            SUT._handle_record('loop', {'dateTime': 1234567890})
            mock_logger.logerr.assert_any_call(SUT.name, "Data queue has size of 10.")

    def test_new_loop_packet_hands_a_deep_copy_to_handle_record(self):
        with self._service() as (SUT, _, _, _):
            SUT._handle_record = mock.Mock()
            packet = {'dateTime': 1234567890, 'outTemp': 70.0}

            SUT.new_loop_packet(mock.Mock(packet=packet))

            args = SUT._handle_record.call_args[0]
            self.assertEqual(args[0], 'loop')
            self.assertIsNot(args[1], packet)
            self.assertDictEqual(args[1], packet)

    def test_new_archive_record_hands_a_deep_copy_to_handle_record(self):
        with self._service() as (SUT, _, _, _):
            SUT._handle_record = mock.Mock()
            record = {'dateTime': 1234567890, 'outTemp': 70.0}

            SUT.new_archive_record(mock.Mock(record=record))

            args = SUT._handle_record.call_args[0]
            self.assertEqual(args[0], 'archive')
            self.assertIsNot(args[1], record)
            self.assertDictEqual(args[1], record)

class _RacingQueue:
    """ A data queue that reproduces the CPython 'Empty while items remain' race.

    get() raises Empty on the first call even though the queue holds items, which
    is the case the drain loop must survive:
    https://github.com/python/cpython/issues/87302#issuecomment-3659919391
    """

    def __init__(self, *items):
        self._queue = Queue.Queue()
        for item in items:
            self._queue.put(item)
        self.gets = 0

    def get(self, timeout=None):
        self.gets += 1
        if self.gets == 1:
            raise Queue.Empty
        return self._queue.get(timeout=timeout)

    def get_nowait(self):
        return self._queue.get_nowait()

    def qsize(self):
        return self._queue.qsize()

    def put(self, item):
        self._queue.put(item)


class TestShutDown(ServiceBase):
    # pylint: disable=protected-access

    def test_drains_queue_then_signals_shutdown_and_stops_thread(self):
        with self._service() as (SUT, _, _, _):
            thread = SUT._thread
            thread.is_alive.return_value = False
            for index in range(3):
                SUT.data_queue.put({'time_stamp': index, 'type': 'loop', 'data': {}})

            SUT.shutDown()

            # Everything pending is consumed, and the shutdown marker is the only item left.
            self.assertEqual(SUT.data_queue.qsize(), 1)
            marker = SUT.data_queue.get_nowait()
            self.assertEqual(marker['type'], 'shutdown')
            self.assertEqual(marker['data'], {})
            # The thread is joined with the configured wait, then released.
            thread.join.assert_called_once_with(SUT.wait_for_thread_shutdown)
            self.assertIsNone(SUT._thread)
            # The logger thread is shut down by the logger itself, with the configured wait.
            SUT.logger.shutdown.assert_called_once_with(SUT.wait_for_thread_shutdown)
            SUT.logger.logerr.assert_not_called()

    def test_drain_retries_when_empty_is_raised_but_items_remain(self):
        with self._service() as (SUT, _, _, _):
            SUT._thread.is_alive.return_value = False
            pending = {'time_stamp': 1, 'type': 'loop', 'data': {}}
            SUT.data_queue = _RacingQueue(pending)

            SUT.shutDown()

            # The false Empty did not end the drain: the pending item was still taken.
            self.assertEqual(SUT.data_queue.gets, 3)
            self.assertEqual(SUT.data_queue.qsize(), 1)
            self.assertEqual(SUT.data_queue.get_nowait()['type'], 'shutdown')
            SUT.logger.logerr.assert_not_called()

    def test_warns_when_thread_does_not_shut_down(self):
        with self._service() as (SUT, _, _, _):
            thread = SUT._thread
            thread.name = helpers.random_string()
            thread.is_alive.return_value = True

            SUT.shutDown()

            SUT.logger.logerr.assert_called_once_with(SUT.name,
                                                      f"Unable to shut down {thread.name}")
            # The reference is dropped even when the thread is still running.
            self.assertIsNone(SUT._thread)

    def test_still_stops_logger_thread_when_no_publishing_thread(self):
        with self._service() as (SUT, _, _, _):
            SUT._thread = None

            SUT.shutDown()

            # The publishing half is skipped entirely.
            self.assertEqual(SUT.data_queue.qsize(), 0)
            # The logger thread is still shut down, via the logger, with the configured wait.
            SUT.logger.shutdown.assert_called_once_with(SUT.wait_for_thread_shutdown)
            SUT.logger.logerr.assert_not_called()

    def test_logs_shutdown_progress_in_order(self):
        with self._service() as (SUT, _, _, _):
            SUT._thread.is_alive.return_value = False
            for index in range(2):
                SUT.data_queue.put({'time_stamp': index, 'type': 'loop', 'data': {}})
            # Drop the version banner logged by __init__.
            SUT.logger.loginf.reset_mock()

            SUT.shutDown()

            messages = [call[0][1] for call in SUT.logger.loginf.call_args_list]
            self.assertEqual(messages[0], "Shutdown initiated")
            self.assertEqual(messages[1], "Emptying data queue with size of 2.")
            self.assertEqual(messages[2], "Data queue has size of 0.")
            self.assertEqual(messages[3], "Shutdown of queue processor initiated")
            self.assertEqual(messages[4], f"Shutdown of logger thread, {SUT.logger.log_thread.name} initiated")

if __name__ == '__main__':
    helpers.run_tests()

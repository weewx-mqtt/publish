#    Copyright (c) 2025-2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name

import configobj

import unittest
import mock

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
                with mock.patch('user.mqttpublish.LoggerThread'):
                    with mock.patch('user.mqttpublish.Logger'):
                        SUT = user.mqttpublish.MQTTPublish(mock_engine, config)

        self.assertTrue(SUT.mqtt_config['log_mqtt'])

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

if __name__ == '__main__':
    helpers.run_tests()

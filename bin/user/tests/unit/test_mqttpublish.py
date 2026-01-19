#    Copyright (c) 2025 Rich Bell <bellrichm@gmail.com>
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

import random

class TestInit(unittest.TestCase):
    def test_PublishWeeWX_stanza_is_deprecated(self):
        mock_engine = mock.Mock()
        config_dict = {
            'MQTTPublish': {
                'PublishWeeWX': {
                    'topics': {}
                }
            }
        }
        config = configobj.ConfigObj(config_dict)

        # with mock.patch('user.mqttpublish.mqtt'):
        with mock.patch('user.mqttpublish.PublishWeeWXThread'):
            with mock.patch('user.mqttpublish.Logger'):
                SUT = user.mqttpublish.MQTTPublish(mock_engine, config)
                SUT.logger.logerr.assert_called_once_with(
                    "'PublishWeeWX' is deprecated. Move options to top level, '[MQTTPublish]'.")

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

                topics_loop, topics_archive = SUT.configure_topics(service_config)

                expected_topics = {
                    topic1: {
                        'qos': 0,
                        'retain': False,
                        'type': 'json',
                        'unit_system': 1,
                        'guarantee_delivery': False,
                        'ignore': False,
                        'append_unit_label': True,
                        'conversion_type': 'string',
                        'format': '%s',
                        'fields': {},
                        'aggregates': {}
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

                topics_loop, topics_archive = SUT.configure_topics(service_config)

                expected_topics = {
                    topic1: {
                        'qos': 0,
                        'retain': False,
                        'type': 'json',
                        'unit_system': 1,
                        'guarantee_delivery': False,
                        'ignore': False,
                        'append_unit_label': True,
                        'conversion_type': 'string',
                        'format': '%s',
                        'fields': {
                            field1: {
                                'name': field1,
                                'unit': None,
                                'ignore': False,
                                'publish_none_value': False,
                                'append_unit_label': True,
                                'conversion_type': 'string',
                                'format_string': '%s'
                            }
                        },
                        'aggregates': {}
                    }
                }

                self.assertDictEqual(topics_loop, expected_topics)
                self.assertDictEqual(topics_archive, expected_topics)

    def test_config_topics_with_aggregates(self):
        mock_engine = mock.Mock()
        config_dict = {
            'MQTTPublish': {
                'enable': False,
            }
        }
        config = configobj.ConfigObj(config_dict)

        topic1 = helpers.random_string()
        aggreagate1 = helpers.random_string()
        period = random.choice(list(user.mqttpublish.period_timespan.keys()))
        service_dict = {
            'topics': {
                topic1: {
                    'aggregates': {
                        aggreagate1: {
                            'period': period,
                        },
                    },
                },
            },
        }
        service_config = configobj.ConfigObj(service_dict)

        with mock.patch('user.mqttpublish.PublishWeeWXThread'):
            with mock.patch('user.mqttpublish.Logger'):
                SUT = user.mqttpublish.MQTTPublish(mock_engine, config)

                topics_loop, topics_archive = SUT.configure_topics(service_config)

                expected_topics = {
                    topic1: {
                        'qos': 0,
                        'retain': False,
                        'type': 'json',
                        'unit_system': 1,
                        'guarantee_delivery': False,
                        'ignore': False,
                        'append_unit_label': True,
                        'conversion_type': 'string',
                        'format': '%s',
                        'fields': {},
                        'aggregates': {
                            aggreagate1: {
                                'period': period,
                                'name': aggreagate1,
                                'unit': None,
                                'ignore': False,
                                'publish_none_value': False,
                                'append_unit_label': True,
                                'conversion_type': 'string',
                                'format_string': '%s'
                            }
                        },
                    }
                }

                self.assertDictEqual(topics_loop, expected_topics)
                self.assertDictEqual(topics_archive, expected_topics)

if __name__ == '__main__':
    helpers.run_tests()

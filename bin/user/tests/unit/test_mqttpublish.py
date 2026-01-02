#    Copyright (c) 2025 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name

import configobj
import logging

import unittest
import mock

import helpers
import user.mqttpublish

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
        logger = logging.getLogger('user.mqttpublish')
        # with mock.patch('user.mqttpublish.mqtt'):
        with mock.patch('user.mqttpublish.PublishWeeWXThread'):
            with mock.patch.object(logger, 'error') as mock_error:
                user.mqttpublish.MQTTPublish(mock_engine, config)
                mock_error.assert_called_once_with(
                    "'PublishWeeWX' is deprecated. Move options to top level, '[MQTTPublish]'.")

class TestConfigureTopics(unittest.TestCase):
    def test_one(self):
        print("start")

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
            with mock.patch('user.mqttpublish.logdbg'):
                user.mqttpublish.MQTTPublish(mock_engine, config)
        print("end")

if __name__ == '__main__':
    helpers.run_tests()

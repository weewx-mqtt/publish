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

import paho.mqtt

import user.mqttpublish

class TestAbstractPublisher(unittest.TestCase):
    def test_get_publisher_for_mqtt_v2(self):

        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        protocol_string = random.choice(['MQTTv31', 'MQTTv311'])

        config_dict = {
            'protocol': getattr(paho.mqtt.client, protocol_string, 0),
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.PublisherV2MQTT3') as mock_client:
            #with mock.patch('builtins.hasattr'):

            user.mqttpublish.AbstractPublisher.get_publisher(mock_logger, mock_publisher, config)

            mock_client.assert_called_once_with(mock_logger, mock_publisher, config)

        print("done")

if __name__ == '__main__':
    helpers.run_tests()

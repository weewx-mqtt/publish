#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name

import helpers
import random

import mock

import configobj
import paho.mqtt
import user.mqttpublish

from user.tests.unit.publisherbase import PublisherBase, TLSBase

# @unittest.skipIf(hasattr(paho.mqtt.client, 'CallbackAPIVersion'), "paho-mqtt is NOT v1, skipping tests.")
class TestPublisherV1(PublisherBase):
    class_under_test = user.mqttpublish.PublisherV1
    protocol_string = random.choice(['MQTTv31', 'MQTTv311'])

    def test_get_client(self):
        mock_logger = mock.Mock()
        mock_publisher = mock.Mock()

        config_dict = {
            'protocol': getattr(paho.mqtt.client, self.protocol_string, 0),
            'clientid': helpers.random_string(),
            'log_mqtt': random.choice([True, False]),
            'username': None,
            'password': None,
            'host': helpers.random_string(),
            'port': random.randint(1, 65535),
            'keepalive': random.randint(1, 30),
            'max_retries': 0,
        }
        config = configobj.ConfigObj(config_dict)

        with mock.patch('user.mqttpublish.time'):
            with mock.patch('user.mqttpublish.mqtt.Client') as mock_client:
                with mock.patch.object(user.mqttpublish.AbstractPublisher, '_connect'):

                    self.class_under_test(mock_logger, mock_publisher, config)

                    mock_client.assert_called_once_with(client_id=config_dict['clientid'], protocol=config_dict['protocol'])

# @unittest.skipIf(hasattr(paho.mqtt.client, 'CallbackAPIVersion'), "paho-mqtt is NOT v1, skipping tests.")
class TestTLS(TLSBase):
    class_under_test = user.mqttpublish.PublisherV1
    protocol_string = random.choice(['MQTTv31', 'MQTTv311'])

# The del is needed to prevent unittest from collecting and running tests in the base class.
# The base class cannot be run directly because it does notdefine the required attributes and will fail.
del PublisherBase, TLSBase

if __name__ == '__main__':
    helpers.run_tests()

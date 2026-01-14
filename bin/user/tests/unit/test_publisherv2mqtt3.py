#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name

import paho.mqtt
import random

import unittest

import helpers

import user.mqttpublish

from test_publisherbase import TemplateBase

@unittest.skipIf(not hasattr(paho.mqtt.client, 'CallbackAPIVersion'), "paho-mqtt is v1, skipping tests.")
class TestTemplate(TemplateBase):
    class_under_test = user.mqttpublish.PublisherV2MQTT3
    protocol_string = random.choice(['MQTTv31', 'MQTTv311'])

# The del is needed to prevent unittest from collecting and running tests in the base class.
# The base class cannot be run directly because it does notdefine the required attributes and will fail.
del TemplateBase

if __name__ == '__main__':
    helpers.run_tests()

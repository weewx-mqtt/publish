#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name

import unittest

import paho.mqtt

import helpers

import user.mqttpublish

from user.tests.unit.publisherbase import PublisherBase

@unittest.skipIf(not hasattr(paho.mqtt.client, 'CallbackAPIVersion'), "paho-mqtt is v1, skipping tests.")
class TestTemplate(PublisherBase):
    class_under_test = user.mqttpublish.PublisherV2
    protocol_string = 'MQTTv5'

# The del is needed to prevent unittest from collecting and running tests in the base class.
# The base class cannot be run directly because it does notdefine the required attributes and will fail.
del PublisherBase

if __name__ == '__main__':
    helpers.run_tests()

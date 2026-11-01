#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name

import importlib
import unittest

import mock

import helpers

import user.mqttcommon
import user.mqttpublish

class TestApiCheck(unittest.TestCase):
    def test_stale_mqttcommon_raises_at_import(self):
        with mock.patch.object(user.mqttcommon, 'MQTTCOMMON_API', (0, 0)):
            with self.assertRaises(ImportError):
                importlib.reload(user.mqttpublish)

if __name__ == '__main__':
    helpers.run_tests()

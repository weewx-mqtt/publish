#    Copyright (c) 2028 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name

import unittest
import mock

import random

import helpers
import user.mqttpublish

class TestLastNDays(unittest.TestCase):
    def test1(self):
        with mock.patch('user.mqttpublish.TimeSpan')as mock_TimeSpan:

            week_start = random.randint(0, 6)
            period_timespans = user.mqttpublish.PeriodTimespan(week_start)

            days = 7
            now = 1771939800
            period_timespans._last_n_days(days, now)

            day_start_timestamp = 1771304400.0
            mock_TimeSpan.assert_called_once_with(day_start_timestamp, now)

if __name__ == '__main__':
    helpers.run_tests()

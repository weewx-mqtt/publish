#    Copyright (c) 2028 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name

import unittest
import mock

import os
import random
import time

import helpers

import user.mqttpublish

class TestGetTimeSpan(unittest.TestCase):
    def test_hour(self):
        with mock.patch('weeutil.weeutil.archiveHoursAgoSpan')as mock_archive_hours_ago_span:
            os.environ['TZ'] = 'America/New_York'
            time.tzset()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttpublish.TimeSpanProvider(week_start)

            now = 1771939800
            timespan_provider.hour(now)

            mock_archive_hours_ago_span.assert_called_once_with(now)

    def test_day(self):
        with mock.patch('weeutil.weeutil.archiveDaySpan')as mock_archive_day_span:
            os.environ['TZ'] = 'America/New_York'
            time.tzset()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttpublish.TimeSpanProvider(week_start)

            now = 1771939800
            timespan_provider.day(now)

            mock_archive_day_span.assert_called_once_with(now)

    def test_yesterday(self):
        with mock.patch('weeutil.weeutil.archiveDaySpan')as mock_archive_day_span:
            os.environ['TZ'] = 'America/New_York'
            time.tzset()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttpublish.TimeSpanProvider(week_start)

            now = 1771939800
            timespan_provider.yesterday(now)

            mock_archive_day_span.assert_called_once_with(now, 1)

    def test_week(self):
        with mock.patch('weeutil.weeutil.archiveWeekSpan')as mock_archive_week_span:
            os.environ['TZ'] = 'America/New_York'
            time.tzset()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttpublish.TimeSpanProvider(week_start)

            now = 1771939800
            timespan_provider.week(now)

            mock_archive_week_span.assert_called_once_with(now, startOfWeek=week_start)

    def test_month(self):
        with mock.patch('weeutil.weeutil.archiveMonthSpan')as mock_archive_month_span:
            os.environ['TZ'] = 'America/New_York'
            time.tzset()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttpublish.TimeSpanProvider(week_start)

            now = 1771939800
            timespan_provider.month(now)

            mock_archive_month_span.assert_called_once_with(now)

    def test_year(self):
        with mock.patch('weeutil.weeutil.archiveYearSpan')as mock_archive_year_span:
            os.environ['TZ'] = 'America/New_York'
            time.tzset()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttpublish.TimeSpanProvider(week_start)

            now = 1771939800
            timespan_provider.year(now)

            mock_archive_year_span.assert_called_once_with(now)

    def test_last24hours(self):
        with mock.patch('user.mqttpublish.TimeSpan')as mock_TimeSpan:
            os.environ['TZ'] = 'America/New_York'
            time.tzset()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttpublish.TimeSpanProvider(week_start)

            now = 1771939800
            timespan_provider.last24hours(now)

            day_start_timestamp = now - 86400
            mock_TimeSpan.assert_called_once_with(day_start_timestamp, now)

    def test_last_n_days(self):
        with mock.patch('user.mqttpublish.TimeSpan')as mock_TimeSpan:
            os.environ['TZ'] = 'America/New_York'
            time.tzset()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttpublish.TimeSpanProvider(week_start)

            days = 7
            now = 1771939800
            timespan_provider._last_n_days(days, now)

            day_start_timestamp = 1771304400.0
            mock_TimeSpan.assert_called_once_with(day_start_timestamp, now)

if __name__ == '__main__':
    helpers.run_tests()

#    Copyright (c) 2025-2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name

import unittest
import mock

import datetime
import os
import random
import time

import helpers

import weeutil
import user.mqttaggregatevalues

class TestGetTimeSpan(unittest.TestCase):
    def setup_timezone(self):
        os.environ['TZ'] = 'America/New_York'
        time.tzset()
        local_dt = datetime.datetime.now().astimezone()
        return local_dt

    def test_hour(self):
        with mock.patch('weeutil.weeutil.archiveHoursAgoSpan')as mock_archive_hours_ago_span:
            os.environ['TZ'] = 'America/New_York'
            time.tzset()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            now = 1771939800
            timespan_provider.hour(now)

            mock_archive_hours_ago_span.assert_called_once_with(now)

    def test_day(self):
        with mock.patch('weeutil.weeutil.archiveDaySpan')as mock_archive_day_span:
            self.setup_timezone()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            now = 1771939800
            timespan_provider.day(now, None)

            mock_archive_day_span.assert_called_once_with(now)

    def test_day_offset_curr_day(self):
        with mock.patch('weeutil.weeutil.archiveDaySpan')as mock_archive_day_span:
            mock_archive_day_span.return_value = weeutil.weeutil.TimeSpan(0, 0)

            local_dt = self.setup_timezone()
            utc_offset = int(local_dt.utcoffset().total_seconds() / 3600)

            now = 1771939800
            current_hour = 13

            week_start = random.randint(0, 6)
            offset = random.randint(1, current_hour + utc_offset)

            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            timespan_provider.day(now, offset)

            mock_archive_day_span.assert_called_once_with(now)

    def test_day_offset_prev_day(self):
        with mock.patch('weeutil.weeutil.archiveDaySpan')as mock_archive_day_span:
            mock_archive_day_span.return_value = weeutil.weeutil.TimeSpan(0, 0)

            local_dt = self.setup_timezone()
            utc_offset = int(local_dt.utcoffset().total_seconds() / 3600)

            now = 1771939800
            current_hour = 13

            week_start = random.randint(0, 6)
            offset = random.randint(current_hour + utc_offset + 1, 23)

            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            timespan_provider.day(now, offset)

            self.assertEqual(mock_archive_day_span.call_count, 2)

    def test_yesterday(self):
        with mock.patch('weeutil.weeutil.archiveDaySpan')as mock_archive_day_span:
            self.setup_timezone()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            now = 1771939800
            timespan_provider.yesterday(now, None)

            mock_archive_day_span.assert_called_once_with(now, 1)

    def test_yesterday_offset_curr_day(self):
        pass

    def test_yesterday_offset_prev_day(self):
        with mock.patch('weeutil.weeutil.archiveDaySpan')as mock_archive_day_span:
            mock_archive_day_span.return_value = weeutil.weeutil.TimeSpan(0, 0)

            local_dt = self.setup_timezone()
            utc_offset = int(local_dt.utcoffset().total_seconds() / 3600)

            now = 1771939800
            current_hour = 13

            week_start = random.randint(0, 6)
            offset = random.randint(current_hour + utc_offset + 1, 23)

            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            timespan_provider.yesterday(now, offset)

            self.assertEqual(mock_archive_day_span.call_count, 2)

    def test_week(self):
        with mock.patch('weeutil.weeutil.archiveWeekSpan')as mock_archive_week_span:
            self.setup_timezone()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            now = 1771939800
            timespan_provider.week(now, None)

            mock_archive_week_span.assert_called_once_with(now, startOfWeek=week_start)

    def test_week_offset_curr_day(self):
        pass

    def test_week_offset_prev_day(self):
        with mock.patch('weeutil.weeutil.archiveWeekSpan')as mock_archive_week_span:
            mock_archive_week_span.return_value = weeutil.weeutil.TimeSpan(0, 0)

            local_dt = self.setup_timezone()
            utc_offset = int(local_dt.utcoffset().total_seconds() / 3600)

            now = 1771939800
            current_hour = 13

            week_start = random.randint(0, 6)
            offset = random.randint(current_hour + utc_offset + 1, 23)

            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            timespan_provider.week(now, offset)

            self.assertEqual(mock_archive_week_span.call_count, 2)

    def test_month(self):
        with mock.patch('weeutil.weeutil.archiveMonthSpan')as mock_archive_month_span:
            self.setup_timezone()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            now = 1771939800
            timespan_provider.month(now, None)

            mock_archive_month_span.assert_called_once_with(now)

    def test_month_offset_curr_day(self):
        pass

    def test_month_offset_prev_day(self):
        with mock.patch('weeutil.weeutil.archiveMonthSpan')as mock_archive_month_span:
            mock_archive_month_span.return_value = weeutil.weeutil.TimeSpan(0, 0)

            local_dt = self.setup_timezone()
            utc_offset = int(local_dt.utcoffset().total_seconds() / 3600)

            now = 1771939800
            current_hour = 13

            week_start = random.randint(0, 6)
            offset = random.randint(current_hour + utc_offset + 1, 23)

            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            timespan_provider.month(now, offset)

            self.assertEqual(mock_archive_month_span.call_count, 2)

    def test_year(self):
        with mock.patch('weeutil.weeutil.archiveYearSpan')as mock_archive_year_span:
            self.setup_timezone()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            now = 1771939800
            timespan_provider.year(now, None)

            mock_archive_year_span.assert_called_once_with(now)

    def test_year_offset_curr_day(self):
        pass

    def test_year_offset_prev_day(self):
        with mock.patch('weeutil.weeutil.archiveYearSpan')as mock_archive_year_span:
            mock_archive_year_span.return_value = weeutil.weeutil.TimeSpan(0, 0)

            local_dt = self.setup_timezone()
            utc_offset = int(local_dt.utcoffset().total_seconds() / 3600)

            now = 1771939800
            current_hour = 13

            week_start = random.randint(0, 6)
            offset = random.randint(current_hour + utc_offset + 1, 23)

            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            timespan_provider.year(now, offset)

            self.assertEqual(mock_archive_year_span.call_count, 2)

    def test_last24hours(self):
        with mock.patch('user.mqttaggregatevalues.TimeSpan')as mock_TimeSpan:
            self.setup_timezone()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            now = 1771939800
            timespan_provider.last24hours(now, None)

            day_start_timestamp = now - 86400
            mock_TimeSpan.assert_called_once_with(day_start_timestamp, now)

    def test_last24hours_offset_curr_day(self):
        pass

    def test_last24hours_offset_prev_day(self):
        with mock.patch('user.mqttaggregatevalues.TimeSpan')as mock_TimeSpan:
            mock_TimeSpan.return_value = weeutil.weeutil.TimeSpan(0, 0)

            local_dt = self.setup_timezone()
            utc_offset = int(local_dt.utcoffset().total_seconds() / 3600)

            now = 1771939800
            current_hour = 13

            week_start = random.randint(0, 6)
            offset = random.randint(current_hour + utc_offset + 1, 23)

            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            timespan_provider.last24hours(now, offset)

            self.assertEqual(mock_TimeSpan.call_count, 2)

    def test_last_n_days(self):
        with mock.patch('user.mqttaggregatevalues.TimeSpan')as mock_TimeSpan:
            self.setup_timezone()

            week_start = random.randint(0, 6)
            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            days = 7
            now = 1771939800
            timespan_provider._last_n_days(days, now)

            day_start_timestamp = 1771304400.0
            mock_TimeSpan.assert_called_once_with(day_start_timestamp, now)

if __name__ == '__main__':
    helpers.run_tests()

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

NOW = 1771939800
CURRENT_HOUR = 13


def make_provider():
    """ A provider with a random week-start day, plus that day for assertions. """
    week_start = random.randint(0, 6)
    return user.mqttaggregatevalues.TimeSpanProvider(None, week_start), week_start


def curr_day_setup(mock_span):
    """ Setup for an offset that still lands on the current local day. """
    mock_span.return_value = weeutil.weeutil.TimeSpan(0, 0)
    utc_offset = int(datetime.datetime.now().astimezone().utcoffset().total_seconds() / 3600)
    offset = random.randint(1, CURRENT_HOUR + utc_offset)
    provider, week_start = make_provider()
    return provider, week_start, offset


def prev_day_setup(mock_span):
    """ Setup for an offset that crosses into the previous local day. """
    start_timestamp = random.randint(10000, 99999)
    stop_timestamp = start_timestamp + random.randint(3600, 7200)
    mock_span.return_value = weeutil.weeutil.TimeSpan(start_timestamp, stop_timestamp)
    utc_offset = int(datetime.datetime.now().astimezone().utcoffset().total_seconds() / 3600)
    offset = random.randint(CURRENT_HOUR + utc_offset + 1, 23)
    provider, week_start = make_provider()
    return provider, week_start, offset, start_timestamp, stop_timestamp


class TestGetTimeSpan(unittest.TestCase):
    def setUp(self):
        self._original_tz = os.environ.get('TZ')
        os.environ['TZ'] = 'America/New_York'
        time.tzset()
        self.addCleanup(self._restore_timezone)

    def _restore_timezone(self):
        if self._original_tz is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = self._original_tz
        time.tzset()

    def test_hour(self):
        with mock.patch('weeutil.weeutil.archiveHoursAgoSpan')as mock_archive_hours_ago_span:
            timespan_provider, _ = make_provider()
            timespan_provider.hour(NOW, None)

            mock_archive_hours_ago_span.assert_called_once_with(NOW)

    def test_day(self):
        with mock.patch('weeutil.weeutil.archiveDaySpan')as mock_archive_day_span:
            timespan_provider, _ = make_provider()
            timespan_provider.day(NOW, None)

            mock_archive_day_span.assert_called_once_with(NOW)

    def test_day_offset_curr_day(self):
        with mock.patch('weeutil.weeutil.archiveDaySpan')as mock_archive_day_span:
            timespan_provider, _, offset = curr_day_setup(mock_archive_day_span)

            timespan_provider.day(NOW, offset)

            mock_archive_day_span.assert_called_once_with(NOW)

    def test_day_offset_prev_day(self):
        with mock.patch('weeutil.weeutil.archiveDaySpan')as mock_archive_day_span:
            timespan_provider, _, offset, start_timestamp, stop_timestamp = prev_day_setup(mock_archive_day_span)

            timespan = timespan_provider.day(NOW, offset)

            self.assertEqual(mock_archive_day_span.call_count, 2)
            self.assertEqual(timespan.start, start_timestamp + offset * 3600)
            self.assertEqual(timespan.stop, stop_timestamp + offset * 3600)

    def test_yesterday(self):
        with mock.patch('weeutil.weeutil.archiveDaySpan')as mock_archive_day_span:
            timespan_provider, _ = make_provider()
            timespan_provider.yesterday(NOW, None)

            mock_archive_day_span.assert_called_once_with(NOW, 1)

    def test_yesterday_offset_curr_day(self):
        with mock.patch('weeutil.weeutil.archiveDaySpan')as mock_archive_day_span:
            timespan_provider, _, offset = curr_day_setup(mock_archive_day_span)

            timespan_provider.yesterday(NOW, offset)

            mock_archive_day_span.assert_called_once_with(NOW, 1)

    def test_yesterday_offset_prev_day(self):
        with mock.patch('weeutil.weeutil.archiveDaySpan')as mock_archive_day_span:
            timespan_provider, _, offset, start_timestamp, stop_timestamp = prev_day_setup(mock_archive_day_span)

            timespan = timespan_provider.yesterday(NOW, offset)

            self.assertEqual(mock_archive_day_span.call_count, 2)
            self.assertEqual(timespan.start, start_timestamp + offset * 3600)
            self.assertEqual(timespan.stop, stop_timestamp + offset * 3600)

    def test_week(self):
        with mock.patch('weeutil.weeutil.archiveWeekSpan')as mock_archive_week_span:
            timespan_provider, week_start = make_provider()
            timespan_provider.week(NOW, None)

            mock_archive_week_span.assert_called_once_with(NOW, startOfWeek=week_start)

    def test_week_offset_curr_day(self):
        with mock.patch('weeutil.weeutil.archiveWeekSpan')as mock_archive_week_span:
            timespan_provider, week_start, offset = curr_day_setup(mock_archive_week_span)

            timespan_provider.week(NOW, offset)

            mock_archive_week_span.assert_called_once_with(NOW, startOfWeek=week_start)

    def test_week_offset_prev_day(self):
        with mock.patch('weeutil.weeutil.archiveWeekSpan')as mock_archive_week_span:
            timespan_provider, _, offset, start_timestamp, stop_timestamp = prev_day_setup(mock_archive_week_span)

            timespan = timespan_provider.week(NOW, offset)

            self.assertEqual(mock_archive_week_span.call_count, 2)
            self.assertEqual(timespan.start, start_timestamp + offset * 3600)
            self.assertEqual(timespan.stop, stop_timestamp + offset * 3600)

    def test_month(self):
        with mock.patch('weeutil.weeutil.archiveMonthSpan')as mock_archive_month_span:
            timespan_provider, _ = make_provider()
            timespan_provider.month(NOW, None)

            mock_archive_month_span.assert_called_once_with(NOW)

    def test_month_offset_curr_day(self):
        with mock.patch('weeutil.weeutil.archiveMonthSpan')as mock_archive_month_span:
            timespan_provider, _, offset = curr_day_setup(mock_archive_month_span)

            timespan_provider.month(NOW, offset)

            mock_archive_month_span.assert_called_once_with(NOW)

    def test_month_offset_prev_day(self):
        with mock.patch('weeutil.weeutil.archiveMonthSpan')as mock_archive_month_span:
            timespan_provider, _, offset, start_timestamp, stop_timestamp = prev_day_setup(mock_archive_month_span)

            timespan = timespan_provider.month(NOW, offset)

            self.assertEqual(mock_archive_month_span.call_count, 2)
            self.assertEqual(timespan.start, start_timestamp + offset * 3600)
            self.assertEqual(timespan.stop, stop_timestamp + offset * 3600)

    def test_year(self):
        with mock.patch('weeutil.weeutil.archiveYearSpan')as mock_archive_year_span:
            timespan_provider, _ = make_provider()
            timespan_provider.year(NOW, None)

            mock_archive_year_span.assert_called_once_with(NOW)

    def test_year_offset_curr_day(self):
        with mock.patch('weeutil.weeutil.archiveYearSpan')as mock_archive_year_span:
            timespan_provider, _, offset = curr_day_setup(mock_archive_year_span)

            timespan_provider.year(NOW, offset)

            mock_archive_year_span.assert_called_once_with(NOW)

    def test_year_offset_prev_day(self):
        with mock.patch('weeutil.weeutil.archiveYearSpan')as mock_archive_year_span:
            timespan_provider, _, offset, start_timestamp, stop_timestamp = prev_day_setup(mock_archive_year_span)

            timespan = timespan_provider.year(NOW, offset)

            self.assertEqual(mock_archive_year_span.call_count, 2)
            self.assertEqual(timespan.start, start_timestamp + offset * 3600)
            self.assertEqual(timespan.stop, stop_timestamp + offset * 3600)

    def test_last24hours(self):
        with mock.patch('user.mqttaggregatevalues.TimeSpan')as mock_TimeSpan:
            timespan_provider, _ = make_provider()
            timespan_provider.last24hours(NOW, None)

            day_start_timestamp = NOW - 86400
            mock_TimeSpan.assert_called_once_with(day_start_timestamp, NOW)

    def test_last24hours_offset_curr_day(self):
        with mock.patch('user.mqttaggregatevalues.TimeSpan')as mock_TimeSpan:
            timespan_provider, _, offset = curr_day_setup(mock_TimeSpan)

            timespan_provider.last24hours(NOW, offset)

            day_start_timestamp = NOW - 86400
            mock_TimeSpan.assert_called_once_with(day_start_timestamp, NOW)

    def test_last24hours_offset_prev_day(self):
        with mock.patch('user.mqttaggregatevalues.TimeSpan')as mock_TimeSpan:
            timespan_provider, _, offset, start_timestamp, stop_timestamp = prev_day_setup(mock_TimeSpan)

            timespan = timespan_provider.last24hours(NOW, offset)

            self.assertEqual(mock_TimeSpan.call_count, 2)
            self.assertEqual(timespan.start, start_timestamp + offset * 3600)
            self.assertEqual(timespan.stop, stop_timestamp + offset * 3600)

    def test_last_n_days(self):
        with mock.patch('user.mqttaggregatevalues.TimeSpan')as mock_TimeSpan:
            week_start = random.randint(0, 6)
            timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)

            days = 7
            timespan_provider._last_n_days(days, NOW)

            day_start_timestamp = 1771304400.0
            mock_TimeSpan.assert_called_once_with(day_start_timestamp, NOW)

    def test_get_timespan_archive_interval(self):
        week_start = random.randint(0, 6)
        timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, week_start)
        offset = random.randint(0, 23)

        timespan = timespan_provider.get_timespan('archive_interval', NOW, offset)

        self.assertIsNone(timespan)

    def test_get_calculation_interval(self):
        timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, 0)

        self.assertEqual(timespan_provider.get_calculation_interval('hour'), 5)
        self.assertEqual(timespan_provider.get_calculation_interval('yesterday'), 60 * 24)

    def test_last7days(self):
        timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, 0)
        timespan = timespan_provider.get_timespan('last7days', NOW, None)

        self.assertEqual(timespan.start, 1771304400.0)
        self.assertEqual(timespan.stop, NOW)

    def test_last31days(self):
        timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, 0)
        timespan = timespan_provider.get_timespan('last31days', NOW, None)

        self.assertEqual(timespan.start, 1769230800.0)
        self.assertEqual(timespan.stop, NOW)

    def test_last366days(self):
        timespan_provider = user.mqttaggregatevalues.TimeSpanProvider(None, 0)
        timespan = timespan_provider.get_timespan('last366days', NOW, None)

        self.assertEqual(timespan.start, 1740286800.0)
        self.assertEqual(timespan.stop, NOW)

if __name__ == '__main__':
    helpers.run_tests()

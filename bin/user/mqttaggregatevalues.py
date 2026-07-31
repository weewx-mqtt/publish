#
#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

""" Plugin to calculate aggregate values. """

import datetime
import time
import traceback

import weewx
import weewx.manager
import weeutil

from weeutil.weeutil import to_bool, to_int, startOfInterval, TimeSpan

class TimeSpanProvider:
    ''' Manage the timespans. '''
    def __init__(self, db_manager, week_start):
        self.db_manager = db_manager
        self.week_start = week_start
        # ToDo: Should calculation interval be something like 'on the archive', 'on the hour', 'on the day'
        # ToDo: Need to think hard about what the interval values should be
        self.period_timespans = {
            # ToDo: This is a special case to try to sum rain increments from loop packets
            'archive_interval': {
                'function': self.archive_interval,
                'calculation_interval': 0,
            },
            'hour': {
                'function': self.hour,
                'calculation_interval': 5,  # Once an archive period # ToDo, need to look this up from the engine
            },
            'day': {
                'function': self.day,
                'calculation_interval': 5,  # Once an archive period # ToDo, need to look this up from the engine
            },
            'yesterday': {
                'function': self.yesterday,
                'calculation_interval': 60 * 24,  # Once a day
            },
            'week': {
                'function': self.week,
                'calculation_interval': 60
            },
            'month': {
                'function': self.month,
                'calculation_interval': 60,
            },
            'year': {
                'function': self.year,
                'calculation_interval': 60,
            },
            'last24hours': {
                'function': self.last24hours,
                'calculation_interval': 60,
            },
            'last7days': {
                'function': self.last7days,
                'calculation_interval': 60,
            },
            'last31days': {
                'function': self.last31days,
                'calculation_interval': 60
            },
            'last366days': {
                'function': self.last366days,
                'calculation_interval': 60,
            },
        }

    def get_timespan(self, interval, timestamp, offset):
        ''' Get a timespan for the interval and timstamp. '''
        return self.period_timespans[interval]['function'](timestamp, offset)

    def get_calculation_interval(self, interval):
        ''' Get a the calculation_interval for an interval. '''
        return self.period_timespans[interval]['calculation_interval']

    def archive_interval(self, _timestamp):
        ''' Handle 'aggregating' over an archive interval. '''
        return None

    def hour(self, timestamp):
        ''' Get a timespan for the hour. '''
        return weeutil.weeutil.archiveHoursAgoSpan(timestamp)

    def day(self, timestamp, offset):
        ''' Get a timespan for the day. '''
        timespan = weeutil.weeutil.archiveDaySpan(timestamp)

        if offset is None:
            return timespan
        return self._adjust_timespan(self.day, timestamp, timespan, offset)

    def yesterday(self, timestamp, offset):
        ''' Get a timespan for yesterday. '''
        timespan = weeutil.weeutil.archiveDaySpan(timestamp, 1)

        if offset is None:
            return timespan
        return self._adjust_timespan(self.yesterday, timestamp, timespan, offset)

    def week(self, timestamp, offset):
        ''' Get a timespan for the running week. '''
        timespan = weeutil.weeutil.archiveWeekSpan(timestamp, startOfWeek=self.week_start)

        if offset is None:
            return timespan
        return self._adjust_timespan(self.week, timestamp, timespan, offset)

    def month(self, timestamp, offset):
        ''' Get a timespan for the running month. '''
        timespan = weeutil.weeutil.archiveMonthSpan(timestamp)

        if offset is None:
            return timespan
        return self._adjust_timespan(self.month, timestamp, timespan, offset)

    def year(self, timestamp, offset):
        ''' Get a timespan for the running year. '''
        timespan = weeutil.weeutil.archiveYearSpan(timestamp)

        if offset is None:
            return timespan
        return self._adjust_timespan(self.year, timestamp, timespan, offset)

    def last24hours(self, timestamp, offset):
        ''' Get a timespan for the last 24 hours. '''
        timespan = TimeSpan(timestamp - 86400, timestamp)

        if offset is None:
            return timespan
        return self._adjust_timespan(self.last24hours, timestamp, timespan, offset)

    def last7days(self, timestamp, offset):
        ''' Get a timespan for the last 7 days. '''
        timespan = self._last_n_days(7, timestamp)

        if offset is None:
            return timespan
        return self._adjust_timespan(self.last7days, timestamp, timespan, offset)

    def last31days(self, timestamp, offset):
        ''' Get a timespan for the last 31 days. '''
        timespan = self._last_n_days(31, timestamp)

        if offset is None:
            return timespan
        return self._adjust_timespan(self.last31days, timestamp, timespan, offset)

    def last366days(self, timestamp, offset):
        ''' Get a timespan for the last 366 days. '''
        timespan = self._last_n_days(366, timestamp)

        if offset is None:
            return timespan
        return self._adjust_timespan(self.last366days, timestamp, timespan, offset)

    def alltime(self, timestamp, offset):
        ''' Get a timespan for alltime. '''
        timespan = weeutil.weeutil.TimeSpan(self.db_manager.firstGoodStamp(), timestamp)

        if offset is None:
            return timespan
        return self._adjust_timespan(self.alltime, timestamp, timespan, offset)

    def _last_n_days(self, days, timestamp):
        return TimeSpan(time.mktime((datetime.date.fromtimestamp(timestamp) - datetime.timedelta(days=days)).timetuple()), timestamp)

    def _adjust_timespan(self, create_timespan, timestamp, timespan, offset):
        seconds_in_day = 24 * 60 * 60
        offset_seconds = offset * 3600
        utc_offset = int((datetime.datetime.now().astimezone().utcoffset().seconds - seconds_in_day) / 3600)
        current_hour = int((timestamp % 86400) // 3600)

        if current_hour + utc_offset >= offset:
            return weeutil.weeutil.TimeSpan(timespan.start + offset_seconds, timespan.stop + offset_seconds)

        # Create another timespan with the adjusted timetamp
        # This will create it with the correct day (start and stop for the given day)
        adjusted_timespan = create_timespan(timestamp - seconds_in_day, None)

        # And now adjust it with the offset
        return weeutil.weeutil.TimeSpan(adjusted_timespan.start + offset_seconds, adjusted_timespan.stop + offset_seconds)

class MQTTAggregateValues:
    """ Calculate aggregate values. """
    def __init__(self, logger, name, plugin_dict, _mqtt_dict, _topics, weewx_dict):
        self.logger = logger
        self.name = name
        self.plugin_dict = weeutil.config.deep_copy(plugin_dict)
        self.enabled = to_bool(self.plugin_dict.get('enable', True))

        if not self.enabled:
            self.logger.loginf(f"Plugin {self.name} is not enabled.")
            return

        self.offset = to_int(plugin_dict.get('offset'))
        self.db_manager = weewx.manager.open_manager(weewx_dict['manager_dict'])
        self.timespan_provider = TimeSpanProvider(self.db_manager,
                                                  weewx_dict['stn_info'].week_start)

        self.last_calculated = {}

        utc_offset = datetime.datetime.now().astimezone().utcoffset().seconds - (60 * 60 * 24)
        for topic in self.plugin_dict['topics']:
            self.last_calculated[topic] = {}
            for (aggregate_observation, aggregate) in self.plugin_dict['topics'][topic].items():
                if to_bool(aggregate.get('enable', True)) \
                    and aggregate['period'] not in self.timespan_provider.period_timespans:
                    self.logger.logerr(f"Invalid 'period', {aggregate['period']}")
                    raise ValueError(f"Invalid 'period', {aggregate['period']}")
                if 'calculation_interval' not in aggregate:
                    aggregate['calculation_interval'] = self.timespan_provider.get_calculation_interval(aggregate['period'])
                aggregate['calculation_interval'] = to_int(aggregate['calculation_interval']) * 60

                if aggregate['calculation_interval'] == 60 * 60 * 24:
                    adjustment = utc_offset
                else:
                    adjustment = 0

                self.last_calculated[topic][aggregate_observation] = {
                    'value': None,
                    'interval_end': None,
                    'adjustment': adjustment,
                }

    def get_callbacks(self):
        """ The callbacks. """
        if not self.enabled:
            return []

        return [
            {
                'update_record': {
                    'timing': 'immediate',
                    'callback': self.update_record
                },
            },
        ]

    def update_record(self, _mqtt_client, topic, data, _units, _qos, _retain):
        """ Run code when MQTT record is updated. """
        now = round(time.time())
        aggregates = {}

        if topic not in self.plugin_dict['topics']:
            return
        aggregate_dict = self.plugin_dict['topics'][topic]

        for aggregate_observation in aggregate_dict:
            if not to_bool(aggregate_dict[aggregate_observation].get('enable', True)):
                continue

            now_adjusted = now + self.last_calculated[topic][aggregate_observation]['adjustment']

            time_span = self.timespan_provider.get_timespan(aggregate_dict[aggregate_observation]['period'],
                                                            data.get('dateTime', now),
                                                            self.offset)
            interval_end = startOfInterval(now_adjusted, aggregate_dict[aggregate_observation]['calculation_interval']) + \
                aggregate_dict[aggregate_observation]['calculation_interval']

            if self.last_calculated[topic][aggregate_observation]['interval_end'] is None or \
                interval_end > self.last_calculated[topic][aggregate_observation]['interval_end']:
                try:
                    aggregate_value_tuple = \
                        weewx.xtypes.get_aggregate(aggregate_dict[aggregate_observation]['observation'],
                                                   time_span, aggregate_dict[aggregate_observation]['aggregation'],
                                                   self.db_manager)
                    # ToDo: only do once?
                    #  unit_type, group = weewx.units.getStandardUnitType(db_manager.std_unit_system, obs_type, aggregate_type)
                    weewx.units.obs_group_dict[aggregate_observation] = aggregate_value_tuple[2]

                    aggregates[aggregate_observation] = aggregate_value_tuple[0]

                    self.last_calculated[topic][aggregate_observation]['value'] = aggregates[aggregate_observation]
                    self.last_calculated[topic][aggregate_observation]['interval_end'] = interval_end

                except (weewx.CannotCalculate, weewx.UnknownAggregation, weewx.UnknownType) as exception:
                    self.logger.logerr(f"Aggregation failed: {exception}")
                    self.logger.logerr(traceback.format_exc())

            aggregates[aggregate_observation] = self.last_calculated[topic][aggregate_observation]['value']

        data.update(aggregates)

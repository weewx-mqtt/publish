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

from weeutil.weeutil import to_bool, TimeSpan

class TimeSpanProvider:
    ''' Manage the timespans. '''
    def __init__(self, week_start):
        self.week_start = week_start
        self.period_timespans = {
            'hour': self.hour,
            'day': self.day,
            'yesterday': self.yesterday,
            'week': self.week,
            'month': self.month,
            'year': self.year,
            'last24hours': self.last24hours,
            'last7days': self.last7days,
            'last31days': self.last31days,
            'last366days': self.last366days,
        }

    def get_timespan(self, interval, timestamp):
        ''' Get a timespan for the interval and timstamp. '''
        return self.period_timespans[interval](timestamp)

    def hour(self, timestamp):
        ''' Get a timespan for the hour. '''
        return weeutil.weeutil.archiveHoursAgoSpan(timestamp)

    def day(self, timestamp):
        ''' Get a timespan for the day. '''
        return weeutil.weeutil.archiveDaySpan(timestamp)

    def yesterday(self, timestamp):
        ''' Get a timespan for yesterday. '''
        return weeutil.weeutil.archiveDaySpan(timestamp, 1)

    def week(self, timestamp):
        ''' Get a timespan for the running week. '''
        return weeutil.weeutil.archiveWeekSpan(timestamp, startOfWeek=self.week_start)

    def month(self, timestamp):
        ''' Get a timespan for the running month. '''
        return weeutil.weeutil.archiveMonthSpan(timestamp)

    def year(self, timestamp):
        ''' Get a timespan for the running year. '''
        return weeutil.weeutil.archiveYearSpan(timestamp)

    def last24hours(self, timestamp):
        ''' Get a timespan for the last 24 hours. '''
        return TimeSpan(timestamp - 86400, timestamp)

    def last7days(self, timestamp):
        ''' Get a timespan for the last 7 days. '''
        return self._last_n_days(7, timestamp)

    def last31days(self, timestamp):
        ''' Get a timespan for the last 31 days. '''
        return self._last_n_days(31, timestamp)

    def last366days(self, timestamp):
        ''' Get a timespan for the last 366 days. '''
        return self._last_n_days(366, timestamp)

    def _last_n_days(self, days, timestamp):
        return TimeSpan(time.mktime((datetime.date.fromtimestamp(timestamp) - datetime.timedelta(days=days)).timetuple()), timestamp)

class MQTTAggregateValues:
    """ Calculate aggregate values. """
    def __init__(self, logger, name, plugin_dict, weewx_dict):
        # ToDo need to add 'enable flag'
        self.logger = logger
        self.name = name
        self.plugin_dict = plugin_dict
        self.enabled = to_bool(self.plugin_dict.get('enable', True))

        self.timespan_provider = TimeSpanProvider(weewx_dict['stn_info'].week_start)

        for topic in self.plugin_dict['topics']:
            for (_, aggregate) in self.plugin_dict['topics'][topic].items():
                if to_bool(aggregate.get('enable', True)) \
                    and aggregate['period'] not in self.timespan_provider.period_timespans:
                    self.logger.logerr(f"Invalid 'period', {aggregate['period']}")
                    raise ValueError(f"Invalid 'period', {aggregate['period']}")

        self.db_manager = weewx.manager.open_manager(weewx_dict['manager_dict'])

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

    def update_record(self, _mqtt_client, topic, data, _qos, _retain):
        """ Run code when MQTT record is updated. """
        aggregates = {}

        if topic not in self.plugin_dict['topics']:
            return
        aggregate_dict = self.plugin_dict['topics'][topic]

        for aggregate_observation in aggregate_dict:
            if not to_bool(aggregate_dict[aggregate_observation].get('enable', True)):
                continue

            time_span = self.timespan_provider.get_timespan(aggregate_dict[aggregate_observation]['period'],
                                                            data['dateTime'])

            try:
                aggregate_value_tuple = \
                    weewx.xtypes.get_aggregate(aggregate_dict[aggregate_observation]['observation'],
                                               time_span, aggregate_dict[aggregate_observation]['aggregation'],
                                               self.db_manager)
                # ToDo: only do once?
                #  unit_type, group = weewx.units.getStandardUnitType(db_manager.std_unit_system, obs_type, aggregate_type)
                weewx.units.obs_group_dict[aggregate_observation] = aggregate_value_tuple[2]

                aggregates[aggregate_observation] = aggregate_value_tuple[0]

            except (weewx.CannotCalculate, weewx.UnknownAggregation, weewx.UnknownType) as exception:
                self.logger.logerr(f"Aggregation failed: {exception}")
                self.logger.logerr(traceback.format_exc())

        data.update(aggregates)

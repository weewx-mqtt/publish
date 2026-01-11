---
title: observation-name
parent: Aggregates
nav_order: 1
---

## [[[[[observation-name]]]]] sections

The name of the aggregated observation in the MQTT payload.
This can be any name.
For example: rainSumDay, outTempMinHour, etc.

### enable

Whether the aggregated value is published or not.
Valid values are `true` or `false`.
The default value is `true`.

### observation

The WeeWX observation to aggregate, rain, outTemp, etc,

### aggregation

The type of aggregation to perform.
See, [https://www.weewx.com/docs/customizing.htm#aggregation_types](https://www.weewx.com/docs/customizing.htm#aggregation_types)

### period

The time period over which the aggregation should occurr.
Valid values are `hour`, `day`, `week`, `month`, `year`, `yesterday`, `last24hours`, `last7days`, `last31days`, or `last366days`.

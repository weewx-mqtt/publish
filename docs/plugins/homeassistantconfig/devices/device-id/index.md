---
title: device-id
parent: devices
nav_order: 1
---
{% include plugins_warning.html %}

## The `[[deviceid]]` section

Each `device-id` subsection is a separate Home Assistant device.

### qos

The MQTT qos when publishing the device discovery message.
Valid values: `0`, `1`, `2`
Default is `0`.

### retain

The retain value when publishing the device discovery message.
Valid values: `true` or `false`
Default is `false`.

### state_topic

The topic that the sensor data is published to.
The default is `weather/loop`

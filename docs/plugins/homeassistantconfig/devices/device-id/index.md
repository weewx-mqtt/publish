---
title: device-id
parent: devices
ancestor: MQTTHomeAssistantConfig
nav_order: 1
---
{% include plugins_warning.html %}

## The [[[device-id]]] section

Each `device-id` subsection is a separate Home Assistant device.
At least one `device-id` subsection must be configured.

### qos

The MQTT qos when publishing the device discovery message.
Valid values: `0`, `1`, `2`
Default is `0`.

### retain

The retain value when publishing the device discovery message.
Valid values: `true` or `false`
Default is `false`.

### ignore_fields

A comma separated list of WeeWX fields that should not be configured in Home Assistant.
The default is an empty list.

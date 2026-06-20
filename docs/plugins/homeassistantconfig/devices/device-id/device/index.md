---
title: device
parent: device-id
ancestor: MQTTHomeAssistantConfig
nav_order: 1
---
{% include plugins_warning.html %}

The device option of the MQTT discovery payload.
Settings in this subsection map directly to the Home Assistant options.
For additional information see, https://www.home-assistant.io/integrations/sensor.mqtt/#device.

## The `[[[[[[device]]]]]]` section

### name

The one of two `device` option required by MQTTHomeAssistantConfig.
The default value is `WeeWX`.

### identifiers

The second `device` option required by MQTTHomeAssistantConfig.
Default is the `device_id` of the device.

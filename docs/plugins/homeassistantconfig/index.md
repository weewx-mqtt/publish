---
title: MQTTHomeAssistantConfig
parent: Plugins
nav_order: 1
---
{% include plugins_warning.html %}

MQTTHomeAssistantConfig uses the [device discovery](https://www.home-assistant.io/integrations/mqtt/#device-discovery-payload) functionality of the MQTT integration.
This is a single json message with all of the sensors for a given device.
Multiple devices are supported by publishing to multiple topics.

Each time a new WeeWX observation (HA sensor) is published, it is added to the discovery message and the updated message is sent.

MQTTHomeAssistantConfig subscribes to HA's "birth message".
If a "birth message" is received, the discovery message is resent.
This eliminates the need to publish the discovery message with `retain = True`.

The sensor's `uniqe_id` is set to the name of the WeeWX observation.

The sensor's `name` is sourced from [WeeWX's labels](https://weewx.com/docs/5.0/custom/custom-reports/?h=label#changing-labels).

MQTTHomeAssistantConfig does a lookup to convert units from WeeWX nomenclature to Home Assistant nomenclature.

MQTTHomeAssistantConfig does a lookup to set the Home Assistant `device_class` based on the WeeWX observation.

The data is sent as json.
The challenge is that Home Assistant expects that every sensor have a value in the json.
It also makes it unreasonable to publish with `retain = True`.
Because of this, in the future the data may be sent individually.

MQTTHomeAssistantConfig can be configured to support additional sensors, override 'default' device_class, unique_ids, names, etc.

## The `[[[MQTTHomeAssistantConfig]]]` section

### module

The module must be set to: `user.mqtthaconfig`.

### enable

Whether the service is enabled or not.
Valid values: `true` or `false`
Default is `true`.

### qos

MQTT qos when subscribing to the birth and lwt topics.
Valid values: `0`, `1`, `2`
Default is `0`

### birth_topic

The Home Assistant birth topic.
Default is `homeassistant/status`

### lwt_topic

The Home Assistant lwt topic.
Default is `homeassistant/status`.

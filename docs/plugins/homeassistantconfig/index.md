---
title: MQTTHomeAssistantConfig
parent: Plugins
nav_order: 1
---
{% include plugins_warning.html %}

MQTTHomeAssistantConfig uses the [device discovery](https://www.home-assistant.io/integrations/mqtt/#device-discovery-payload) functionality of the MQTT integration.
This is a single json message with all of the sensors for a given device.
Multiple Home Assistant devices can be configured.
Each device has its own MQTT discovery message.
A device can subscribe to multiple MQTT state topics.

A design goal is to need very little configuration to use the functionality, but to make additional customization easily configured.
The following is the smallest required configuration information

``` text
[MQTTPublish]
    [[plugins]]
        [[[MQTTHomeAssistantConfig]]]
            [[[[devices]]]]
                [[[[[REPLACE_ME_DEVICE]]]]]
                    [[[[[[topics]]]]]]
                        [[[[[[[REPLACE_ME_TOPIC]]]]]]]

```

This will create the device REPLACE_ME_DEVICE in Home Assistant.
All of the fields published to the REPLACE_ME_TOPIC will be sensors associated with the device.
By default the data published to REPLACE_ME_TOPIC is expected to be json.
But, this can be configured for each WeeWX field to be published individually to topics named, REPLACE_ME_TOPIC/fieldname.

THe following Home Assistant data is automatically derived from the data in WeeWX.

- The sensor's `unique_id` is set to the name of the WeeWX observation.
- The sensor's `name` is sourced from [WeeWX's labels](https://weewx.com/docs/5.0/custom/custom-reports/?h=label#changing-labels).
- The sensor's `device_class` is set based on the WeeWX fieldname.
- The sensor's units is set based on the units of the WeeWX data.

All of these 'default' settings are easily overridden.
In addition, it is easy to configure additional WeeWX fieldname to Home Assistant sensor mapping.

MQTTHomeAssistantConfig subscribes to HA's "birth message".
If a "birth message" is received, the discovery message is resent.
This eliminates the need to publish the discovery message with `retain = True`.
But, the `retain = True` setting can easily be overridden.

## The `[[[MQTTHomeAssistantConfig]]]` section

### module

The module must be set to: `user.mqtthaconfig`.

### enable

Whether the plugin is enabled or not.
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

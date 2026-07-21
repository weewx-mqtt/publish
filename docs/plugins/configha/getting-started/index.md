---
title: Getting Started
parent: MQTTConfigHA
ancestor: MQTTConfigHA
nav_order: 1
---
{% include configha_warning.html %}

MQTTConfigHA uses the [device discovery](https://www.home-assistant.io/integrations/mqtt/#device-discovery-payload) functionality of the MQTT integration.
This is a single json message with all of the components for a given device.
This configuration data is published to Home Assistant in addition to the WeeWX weather data being published.
This configuration data is often referred to as the 'MQTT discovery message.'
The WeeWX weather data is 'inspected' to create the 'MQTT discovery message'.

A design goal is to need very little configuration to use the functionality, but to make additional customization easily configured.
The minimum information MQTTConfigHA needs is the name of the topic with the WeeWX data and the of the Home Assistant device that is to be configured. This would look something like this configuration skeleton.
The topic that the WeeWX data is published to is called the `state_topic`.

``` text
[MQTTPublish]

...

    [[topics]]
        [[[REPLACE_ME_TOPIC]]]

        ...


[MQTTConfigHA]]
    [[device]]]
        [[[REPLACE_ME_DEVICE]]]
            [[[[topics]]]]
                # Note this topic, REPLACE_ME_TOPIC, must under the [MQTTPublish][[topics]] section
                [[[[[REPLACE_ME_TOPIC]]]]]

```

This will create the device REPLACE_ME_DEVICE in Home Assistant.
All of the WeeWX fields published to the REPLACE_ME_TOPIC will be components associated with the device.
By default the data published to REPLACE_ME_TOPIC is expected to be json.
But, this can be configured for each WeeWX field to be published individually to topics named, REPLACE_ME_TOPIC/fieldname.

THe following Home Assistant data is automatically derived from the data in WeeWX.

- The `device_class` is set based on the WeeWX fieldname.
- The `name` is sourced from [WeeWX's labels](https://weewx.com/docs/5.0/custom/custom-reports/?h=label#changing-labels).
- The `platform` is set `sensor`.
- The `state_class` is based on the the name (barometer, outTemp, etc.) of the WeeWX data.
- The `unique_id` is set to the device_id concatentated with the name of the WeeWX observation.
- The `unit_of_measurement` is set based on the units of the WeeWX data.
- The `value_template` depends on whether json or 'individual' data is being published. {% raw %}
For json payloads it is set to, `{{ value_json."compoent-id" | default(this.state) }}`.
For individual payloads it is set to `{{ value }}`.
{% endraw %}

All of these 'default' settings are easily overridden.
In addition, it is easy to configure additional WeeWX fieldname to Home Assistant component mapping.

MQTTConfigHA subscribes to HA's "birth message".
If a "birth message" is received, the discovery message is resent.
This eliminates the need to publish the discovery message with `retain = True`.
But, the `retain = True` setting can easily be overridden.

---
title: Binary Sensor
parent: Examples
ancestor: MQTTHomeAssistantConfig
nav_order: 1
---
{% include plugins_warning.html %}

Out of the box, MQTTHomeAssistantConfig supports device discovery for Home Assistant `sensor` data.
This is an example of using MQTTHomeAssistantConfig for a Home Assistant `binary sensor` data.

``` text
[MQTTPublish]
    plugins = MQTTConfigHa
    .
    .
    .
    [[topics]]
        [[weather/loop3]]
        .
        .
        .
[MQTTConfigHA]
    .
    .
    .
    [[devices]]
        # The device-id. Can be any valid Home Assistant value.
        [[[device001]]]
            # A comma separated list of published fields that should NOT be configured as Home Assistant components.
            ignore_fields = interval
            [[[[device]]]]
                # The name of this device
                name = Water Detectors

            # The topics that source Home Assistant.
            [[[[topics]]]]
                [[[[[weather/loop3]]]]]
                    # The 'type' of payload.
                    type = individual

            # Data to define the component to Home Assistant.
            # Observations known to WeeWX can have default values overridden.
            # Observations that have been added to WeeWX can be defined here.
            # IGNORE this section until you have something up and running in HA and want to 'tweak' it.
            [[[[component_data]]]]
                # The WeeWX observeration name that is published to MQTT.
                # This is an observation that has been added to WeeWX
                [[[[[leak_mon1]]]]]
                    # Data used by Home Assistant to configue this device follow.
                    name = Shed
                    platform = binary_sensor
                    payload_off = 0
                    payload_on = 1
```

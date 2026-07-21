---
title: component_data
parent: device-id
ancestor: MQTTConfigHA
nav_order: 4
---
{% include plugins_warning.html %}

## The `[[[[component_data]]]]` section

The options below are set by MQTTConfigHA.
These can easily be overriden in `weewx.conf`.
Additional options can also be set in `weewx.conf`.

These MQTTConfigHA options can be overridden in [`[[[[defaults]]]]` section](defaults/index.md).
This will override the settings for all components belonging to this device.

Using the [`[[[[component-id]]]]` section](component-id/index.md), the settings can be overridden for the specific `component-id` to WeeWX mappings.

### device_class

### name

The name of the MQTT component.
It defaults to the WeeWX label.
If there is no WeeWX label, it is set to the `component-id`.

### platform

It is set to `sensor`.

The device_class of the component.
This is set by looking up the value for the given WeeWX fieldname.
The lookup 'table' can be found at the beginnng of the `mqtthaconfig.py` file.

### state_class

The state_class of the component.
This is set by looking up the value for the given WeeWX fieldname.
The lookup 'table' can be found at the beginnng of the `mqtthaconfig.py` file.

### state_topic

The MQTT topic subscribed to receive component values.
Set to the MQTTPublish topic the data is being published to.

### unique_id

An ID that uniquely identifies this component.
Set to the `device_id_component-id`.

### unit_of_measureent

Defines the units of measurement of the component, if any.
This is set by mapping the WeeWX unit to the HA unit.
The lookup 'table' can be found near the beginnng of the `mqtthaconfig.py` file.

### value_template

Defines the template to extract the value.
{% raw %}
For json payloads it is set to, `{{ value_json."compoent-id" | default(this.state) }}`
For individual payloads it is set to `{{ value }}`
{% endraw %}

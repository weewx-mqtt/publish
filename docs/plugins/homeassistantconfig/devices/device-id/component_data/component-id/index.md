---
title: component-id
parent: component_data
ancestor: MQTTHomeAssistantConfig
nav_order: 1
---
{% include plugins_warning.html %}

## The `[[[[[[[component-id]]]]]]]` section

The following options are set by MQTTHomeAssistantConfig.
These can easily be overriden in `weewx.conf`.
Additional options can be set in `weewx.conf`.

### device_class

The type/class of the sensor.
This is set by looking up the value for the given WeeWX fieldname.
The lookup 'table' can be found at the beginnng of the `mqtthaconfig.py` file.

### state_class

The type/class of the sensor state.
This is set by looking up the value for the given WeeWX fieldname.
The lookup 'table' can be found at the beginnng of the `mqtthaconfig.py` file.

### unit_of_measureent

Defines the units of measurement of the sensor, if any.
This is set by mapping the WeeWX unit to the HA unit.
The lookup 'table' can be found near the beginnng of the `mqtthaconfig.py` file.

### unique_id

An ID that uniquely identifies this sensor.
Set to the `device_id_component-id`.

### state_topic

The MQTT topic subscribed to receive sensor values.
Set to the MQTTPublish topic the data is being published to.

### value_template

Defines the template to extract the value.
{% raw %}
For json payloads it is set to, `{{ value_json."compoent-id" | default(this.state) }}`
For individual payloads it is set to `{{ value }}`
{% endraw %}

### name

The name of the MQTT sensor.
It defaults to the WeeWX label.
If there is no WeeWX label, it is set to the `component-id`.

### platform

It is set to `sensor`.

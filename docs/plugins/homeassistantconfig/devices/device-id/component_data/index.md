---
title: component_data
parent: device-id
ancestor: MQTTHomeAssistantConfig
nav_order: 1
---
{% include plugins_warning.html %}

## The `[[[[[[component_data]]]]]]` section

Each `component-id` subsection can be used to override existing WeeWX fieldname to sensor mapping;
or to define new ones.
The `component-id` must the name of a field in the MQTT payload.

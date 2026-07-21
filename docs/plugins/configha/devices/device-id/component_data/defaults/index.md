---
title: defaults
parent: component_data
ancestor: MQTTConfigHA
nav_order: 1
---
{% include configha_warning.html %}

## The `[[[[[defaults]]]]]` section

Each `default` subsection can be used to override existing WeeWX fieldname to component mapping;
or to define new ones.
This will set the option for all components (WeeWX fields) belonging to the device.
These could be overridden for an individual component via the [`[[[[component-id]]]]` section](component-id/index.md).

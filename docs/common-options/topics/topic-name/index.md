---
title: topic-name
parent: topics
ancestor: Configuring MQTTPublish
nav_order: 1
---

## [[[topic-name]]] sections

### A default value can be set at the top level for these options

#### [qos]({{ site.baseurl }}{% link common-options/index.md %}/#qos)

The QOS level to publish to.

#### [retain]({{ site.baseurl }}{% link common-options/index.md %}/#retain)

The MQTT retain flag.
Valid values are `true` or `false`.

#### [type]({{ site.baseurl }}{% link common-options/index.md %}/#type)

The format of the MQTT payload.
Valid values are `individual`, `json`, or `keyword`.

### These options set a default value for the fields of this topic and override values set at the top level

#### [append_unit_label]({{ site.baseurl }}{% link common-options/index.md %}/#append_unit_label)

Controls if the Weewx unit label should be appended to the data being published.
Valid values are `true` or `false`.

#### [conversion_type]({{ site.baseurl }}{% link common-options/index.md %}/#conversion_type)

The data type conversion to apply to the data being published.

#### [format_string]({{ site.baseurl }}{% link common-options/index.md %}/#format_string)

The formatting to apply to the data being published.

### These options set a default value for the fields of this topic

#### ignore

Controls if the field should be ignore (not published).
Valid values are `true` or `false`.
Default value is `false`.

#### publish_none_value

Controls if data with a value of `None` should be published.
Valud values are `true` or `false`.
The default value is `false`.

### Options for controlling topic processing

#### binding

The WeeWX event binding.
Valid values are `loop`, `archive`, or `loop, archive`.
The default value is `archive, loop`.

#### ignore_fields

A comma seperated list of fields that are not published.
This is a short hand notation for having to configure each field and setting `ignore = True` in its section.

#### publish

Controls if the topic is published.
Valid values are `true` or `false`.
The default value is `true`.

#### publish_fields

A comma seperated list of fields that are to be published.
This is a short hand notation for having to configure each field and setting `ignore = False` in its section.

#### unit_system

The unit system for data published to this topic.
The default value is `US`.

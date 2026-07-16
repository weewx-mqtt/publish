---
title: field-name
parent: fields
ancestor: Configuring MQTTPublish
nav_order: 1
---

## [[[[[field-name]]]]] sections

### A default value can be set at the topic level for these options

#### [append_unit_label]({{ site.baseurl }}{% link common-options/topics/topic-name/index.md %}/#append_unit_label)

Controls if the Weewx unit label should be appended to the data being published.
Valid values are `true` or `false`.

#### [conversion_type]({{ site.baseurl }}{% link common-options/topics/topic-name/index.md %}/#conversion_type)

The data type conversion to apply to the data being published.

#### [format_string]({{ site.baseurl }}{% link common-options/topics/topic-name/index.md %}/#format_string)

The formatting to apply to the data being published.

#### [ignore]({{ site.baseurl }}{% link common-options/topics/topic-name/index.md %}/#ignore)

Controls if the field should be ignore (not published).
Valid values are `true` or `false`.

#### [publish_none_value]({{ site.baseurl }}{% link common-options/topics/topic-name/index.md %}/#publish_none_value))

Controls if data with a value of `None` should be published.
Valud values are `true` or `false`.

#### [round]({{ site.baseurl }}{% link common-options/topics/topic-name/index.md %}/#round)

The rounding to apply to the data being published.

### Options for controlling field processing

#### name

The WeeWX name of the data to be published.
The default is the config section (field-name) value.

#### unit

The WeeWX unit to convert the data being published to.
Default value is `None`.

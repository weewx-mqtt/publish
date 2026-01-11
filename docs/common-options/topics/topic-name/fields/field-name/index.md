---
title: field-name
parent: Fields
nav_order: 1
---

## [[[[[field-name]]]]] sections

### ignore

Controls if the field should be ignore (not published).
Valid values are `true` or `false`.
Default value is `false`.

### name

The WeeWX name of the data to be published.
The default is the config section (field-name) value.

### unit

The WeeWX unit to convert the data being published to.
Default value is `None`.

### publish_none_value

Controls if data with a value of `None` should be published.
Valud values are `true` or `false`.
The default value is `false`.

### append_unit_label

Controls if the Weewx unit label should be appended to the data being published.
Valid values are `true` or `false`.
The default value is ``true`.

### conversion_type

The data type conversion to apply to the data being published.
The default value is `string`.

### format_string

The formatting to apply to the data being published.
The default value is `%s`.

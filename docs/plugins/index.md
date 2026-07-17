---
title: Plugins
nav_order: 2
---
{% include plugins_warning.html %}

## The `plugins` option

A list of plugins for MQTTPublish.
Each entry must have a corresponding section, `[plugin-name]` in the weewx configuration file.
The `plugin` option in the `[plugin-name]` section must have a value.

## `[plugin-name]` section

The configuration data for plugin, `plugin-name`.

### plugin

The plugin to be used.

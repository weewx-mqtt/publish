---
title: Plugins (Deprecated)
nav_order: 2
---
{% include plugins_warning.html %}

## The `[plugins]` section

MQTTPublish supports adding functionality via 'plugins'.
Each subsection under the `[plugins]` section is the name of a plugin.
MQTTPublish ships with one plugin, `MQTTHomeAssistantConfig`.
This plugin adds support for Home Assistant MQTT auto-discovery.

### `[[[plugin-name]]]` section

#### module

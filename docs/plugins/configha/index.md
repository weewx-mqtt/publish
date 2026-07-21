---
title: MQTTConfigHA
parent: Plugins
nav_order: 1
---
{% include configha_warning.html %}

Not sure where to start, read [getting started](getting-started/index.md).

Below is the detail for configuring MQTTConfigHA

## The `[MQTTConfigHA]` section

### plugin

The plugin to be used.

### enable

Whether the plugin is enabled or not.
Valid values: `true` or `false`
Default is `true`.

### qos

MQTT qos when subscribing to the birth and lwt topics.
Valid values: `0`, `1`, `2`
Default is `0`

### birth_topic

The Home Assistant birth topic.
Default is `homeassistant/status`

### birth_payload

The Home Assistant birth payload.
Default is `online`.

### lwt_topic

The Home Assistant lwt topic.
Default is `homeassistant/status`.

### lwt_payload

The Home Assistant lwt payload.
Default is `offline`.

### discovery_topic_prefix

THe Home Assistant discovery topic prefix.
Default is `homeassistant`.

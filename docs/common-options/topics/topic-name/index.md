---
title: topic-name
parent: Topics
nav_order: 1
---

## [[[topic-name]]] sections

### publish

Controls if the topic is published.
Valid values are `true` or `false`.
The default value is `true`.

### type

The format of the MQTT payload.
Valid values are `individual`, `json`, or `keyword`.
The default value is `json`.

### binding

The WeeWX event binding.
Valid values are `loop`, `archive`, or `loop, archive`.
The default value is `archive, loop`.

### qos

The QOS level to publish to.
The default value is `0`.

### retain

The MQTT retain flag.
Valid values are `true` or `false`.
The default value is `false`.

### unit_system

The unit system for data published to this topic.
The default value is `US`.

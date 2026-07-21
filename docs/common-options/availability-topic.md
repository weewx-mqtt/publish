---
title: availability_topic
parent: Configuring MQTTPublish
nav_order: 2
---

## The `[[availability_topic]]` section

This configures a topic that MQTTPublish uses to publish its availability 'online' or 'offline'. 
Under the covers MQTT LWT function is leveraged for 'offline' messages.

### enable

Turn the availability topic function on and off.
Valid values are `true` or `false`.
The default value is `true`.

### topic

The topic that the availability messages are published on.
The default value is `status`.

### online_payload

The default value is `online`.

### offline_payload

The default value is `offline`.

### qos

The quality of service level to use when publishing the messages..
The default value is `0`.

### retain

If set to `true`, the messages will be set as the "last known good"/retained message for the topic.
Valid values are `true` or `false`.
The default value is `true`.

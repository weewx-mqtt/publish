---
title: LWT
parent: Configuring MQTTPublish
nav_order: 2
---

## The `[[lwt]]` section

### enable

Whether LWT (Last Will and Testament) is enabled or not.
Valid values are `true` or `false`.
The default value is `true`.

### topic

The topic that the will message should be published on.
The default value is `status`.

### online_payload

The default value is `online`.

### offline_payload

The default value is `offline`.

### qos

The quality of service level to use for the will.
The default value is `0`.

### retain

If set to `true`, the will message will be set as the "last known good"/retained message for the topic.
Valid values are `true` or `false`.
The default value is `true`.

---
title: topic-name
parent: topics
ancestor: MQTTMessageTracker
nav_order: 1
---
{% include messagetracker_warning.html %}

## [[[topic-name]]] sections

### enable

Whether to track this topic.
Valid values are `true` or `false`.
Default is `true`.

### retention

How long, in seconds, to keep this topic's `confirmed` and `failed` rows.
Set to `0` to keep them forever.
Default is the plugin-level [retention](../../index.md#retention).

### unconfirmed_retention

How long, in seconds, to keep this topic's `unconfirmed` rows.
Set to `0` to keep them forever.
Default is the plugin-level [unconfirmed_retention](../../index.md#unconfirmed_retention).

```ini
[MQTTMessageTracker]
    [[topics]]
        [[[weather/outTemp_F]]]
            # Keep this topic for a day.
            retention = 86400
        [[[weather/outHumidity]]]
            # Do not track this topic.
            enable = false
```

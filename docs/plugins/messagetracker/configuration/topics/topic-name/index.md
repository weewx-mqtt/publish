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

### confirmed_retention

How long, in seconds, to keep this topic's `confirmed` rows.
Set to `0` to keep them forever.
Default is the plugin-level [confirmed_retention](../../index.md#confirmed_retention).

### error_retention

How long, in seconds, to keep this topic's `failed` and `unconfirmed` rows.
Set to `0` to keep them forever.
Default is the plugin-level [error_retention](../../index.md#error_retention).

```ini
[MQTTMessageTracker]
    [[topics]]
        [[[weather/outTemp_F]]]
            # Keep a day of successful publishes, and every failure until it is recovered.
            confirmed_retention = 86400
            error_retention = 0
        [[[weather/outHumidity]]]
            # Do not track this topic.
            enable = false
```

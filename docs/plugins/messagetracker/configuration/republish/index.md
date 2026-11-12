---
title: republish
parent: Configuration
ancestor: MQTTMessageTracker
nav_order: 2
---
{% include messagetracker_warning.html %}

## The `[[republish]]` section

The automatic republishing options. Republishing is off until `on_startup` or `on_reconnect` is
`true`.

```ini
[MQTTMessageTracker]
    [[republish]]
        on_startup = true
        on_reconnect = true
```

### on_startup

Whether to republish after the first successful connection of the tracker.
Default is `false`.

### on_reconnect

Whether to republish after a reconnect.
Default is `false`.

When both are `false`, the section does nothing.

### include_before_last_success

Whether to republish every `unconfirmed` and `failed` message for a topic, including messages
older than that topic's last confirmed publish.
Default is `false`.

### since

Only republish messages published within the last `since` seconds.
Set to `0` to consider every message after the last confirmed publish.
Default is `0`.

See [Republishing](../../republish/index.md) for when messages are republished, and how
`include_before_last_success` changes the selection.

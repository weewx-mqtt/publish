---
title: republish
parent: Configuration
ancestor: MQTTMessageTracker
nav_order: 2
---
{% include messagetracker_warning.html %}

## The `[[republish]]` section

The automatic resend options. Resending is off until `on_startup` or `on_reconnect` is `true`.

```ini
[MQTTMessageTracker]
    [[republish]]
        on_startup = true
        on_reconnect = true
```

### on_startup

Whether to resend after the first successful connection of the tracker.
Default is `false`.

### on_reconnect

Whether to resend after a reconnect.
Default is `false`.

When both are `false`, the section does nothing.

### include_before_last_success

Whether to resend every `unconfirmed` and `failed` message for a topic, including messages
older than that topic's last confirmed publish.
Default is `false`.

### since

Only resend messages sent within the last `since` seconds.
Set to `0` to consider every message after the last confirmed publish.
Default is `0`.

### limit

The maximum number of messages to resend per connection.
Set to `0` to resend every message.
Default is `0`.

See [Resending](../../republish/index.md) for when messages are resent, and how
`include_before_last_success` changes the selection.

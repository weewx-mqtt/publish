---
title: MQTTMessageTracker
parent: Plugins
nav_order: 4
has_children: true
---
{% include messagetracker_warning.html %}

MQTTMessageTracker records every message MQTTPublish sends to the topics you track in a separate
WeeWX database. Each record holds the outcome of the publish. The tracker can resend the messages
that failed, or whose outcome is unknown, after the connection comes back.

The plugin is optional. Enable it when you want delivery history, automatic resend, or the
`mqtttracker` tool and its `resend`, `prune` and `status` subcommands.

## Enabling it

The install adds a database and binding for the tracker to `weewx.conf`:

```ini
[DataBindings]
    [[message_tracker_binding]]
        database = message_tracker

[Databases]
    [[message_tracker]]
        database_name = mqtt_message_tracker.sdb
        database_type = SQLite
```

`database_type = SQLite` uses the SQLite settings in `[DatabaseTypes]`, so the file lands in the
same directory as the weather archive.
To use another database, change these entries and point `data_binding` at the binding.

The database is created if it does not exist, unless `create_database` is `false`.
If it is created, an empty database is made; the tracker then creates its table.

Then enable the plugin:

```ini
[MQTTPublish]
    plugins = MQTTAggregateValues, MQTTConfigHA, MQTTArchiveValues, MQTTMessageTracker

[MQTTMessageTracker]
    plugin = user.mqttmessagetracker.MQTTMessageTracker
    enable = true
    data_binding = message_tracker_binding
    [[topics]]
        [[[weather/outTemp_F]]]
        [[[weather/outHumidity]]]
```

See [Configuration](configuration/index.md) for every option.

## What is tracked

Each message published to a tracked topic records a row in the tracker table.
A resend is a new row that points at the original with `origin_id` and `attempt`; the original
row is never changed.

Messages published directly by a plugin, such as the Home Assistant discovery messages, and the
availability/LWT message are not tracked.

See [Internals](internals/index.md#what-is-tracked) for the row fields and payload storage.

## What the status means

| status | meaning |
| --- | --- |
| `failed` | paho returned a non-success `rc`; the message was not published. |
| `sent` | the message was handed to paho and its arrival has not been reported yet. |
| `confirmed` | the broker acknowledged the publish; `arrived_ts` is set. |
| `unconfirmed` | no arrival was reported before the tracker stopped waiting; `unconfirmed_ts` is set. |

`sent` is transient: it moves to `confirmed` when paho reports the publish, or to `failed` when paho
refuses it. `unconfirmed` is not proof that the message was not delivered; it means the tracker
could not tell.

A `confirmed` row means the broker accepted the publish:

- with QoS 1, paho reported a PUBACK: the broker received the message;
- with QoS 2, paho reported a PUBCOMP: the broker accepted the message and took ownership of it.
  The exactly-once handshake is with the publisher only; forwarding to subscribers is a separate
  leg, and the publisher is never told what happens on it;
- with either QoS and `retain`, the broker also stored the message as the topic's retained value.

None of these mean that a subscriber received it. QoS is enforced between one client and the
broker, not from publisher to subscriber. See [QoS in detail](qos/index.md).

See [Internals](internals/index.md#status-lifecycle) for when rows are marked `unconfirmed`, and
for the message-id reuse behavior.

## QoS and duplicate delivery

QoS 2 is exactly-once between one client and the broker, and separately between the broker and
each subscriber. It is not an end-to-end guarantee across reconnects, restarts, or application
retries, and it does not mean a subscriber received the message.

A resend is a new publish with a new packet id. The broker cannot tell that it is a replay, so a
subscriber can receive the same application message more than once, even when the topic uses
QoS 2. This applies to both automatic resend and `mqtttracker resend`.

The tracker therefore provides at-least-once delivery end to end. Consumers must be idempotent,
for example by deduplicating on `dateTime`. `failed` rows are safe to resend: paho refused them,
so they were not published. `unconfirmed` rows are the ambiguous ones: the original may have
reached the broker, but its acknowledgement was not observed.

See [QoS in detail](qos/index.md) for the packet-level handshakes, the per-leg guarantees, and a
worked example with a subscriber that never acknowledges.

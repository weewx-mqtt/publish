---
title: MQTTMessageTracker
parent: Plugins
nav_order: 4
---
{% include plugins_warning.html %}

## The `[MQTTMessageTracker]` section

### plugin

The plugin to be used.

### enable

Whether the plugin is enabled or not.
Valid values: `true` or `false`
Default is `true`.

### data_binding

The WeeWX data binding that identifies the separate database to write to.
Required; there is no default, so the tracker never writes to the weather database by accident.

### create_database

Whether to create the database if it does not exist.
Valid values: `true` or `false`
Default is `true`.

### table

The name of the table to create and write to.
Default is `mqtt_message_tracker`.

### retention

How long, in seconds, to keep rows.
Set to `0` to keep them forever.
Default is `604800` (7 days).

### prune_interval

How often, in seconds, to delete rows older than `retention`.
Default is `3600`.

### queue_size

The maximum number of events to queue before they are dropped.
The queue is drained by a background thread.
Default is `10000`.

### batch_size

The maximum number of events written in one transaction.
Default is `100`.

### pending_ttl

How long, in seconds, to keep an arrival that arrived before its send event.
This can happen because the MQTT callback and the publishing code run on different threads.
Default is `60`.

### shutdown_timeout

How long, in seconds, to wait for the tracker thread to write its queue and stop.
Default is `10`.

## What is tracked

Each message published by the data pipeline records a row.

- `id`: a unique id for the row.
- `mid`: the MQTT message id.
- `dateTime`: the WeeWX timestamp of the data.
- `sent_ts`: when the message was handed to paho.
- `arrived_ts`: when paho reported it published, `NULL` for anything that is not `acked`.
- `status`: what is known about the message, see below.
- `unconfirmed_ts`: when the tracker stopped waiting for the arrival, `NULL` unless the status is `unconfirmed`.
- `topic`: the topic the message was published on.
- `qos`: the quality of service level used.
- `retain`: whether the message is retained.
- `rc`: the paho result code.
- `payload`: the payload that was sent.

The payload is stored as text; binary payloads are hex-encoded.
With MySQL, `MEDIUMTEXT` holds up to 16 MB; SQLite has no practical limit.
A larger payload makes the insert fail and the batch is logged and dropped.

Messages published directly by a plugin, such as the Home Assistant discovery messages, and the
availability/LWT message are not tracked.

## What the status means

| status | meaning |
| --- | --- |
| `failed` | paho returned a non-success `rc`; the message was not published. |
| `sent` | the message was handed to paho and its arrival has not been reported yet. |
| `acked` | paho reported the message as published; `arrived_ts` is set. |
| `unconfirmed` | no arrival was reported before the tracker stopped waiting; `unconfirmed_ts` is set. |

`sent` is transient. While the tracker is running, a row is expected to move to `acked`, or to
`failed` when paho refuses the publish.

`unconfirmed` does not mean the message was not delivered. It means the tracker cannot tell: paho
never reported the arrival, and no further report can arrive. That is why it is recorded as its own
status instead of an empty `arrived_ts`.

Rows are closed as `unconfirmed`:

- when the publishing thread stops and paho has not reported the arrival, with `unconfirmed_ts`
  set to the shutdown time. This includes messages that were delivered but whose arrival was not
  reported before the process stopped;
- when paho reuses a message id before the arrival of the older message is reported, with
  `unconfirmed_ts` set to the time of the reuse;
- at startup, for the rows a previous run left in `sent`, with `unconfirmed_ts` set to the startup
  time. This covers a process that stopped without shutting down cleanly.

An `acked` row is also not proof of delivery to a subscriber:

- with QoS 0, paho reports the message once it is written to the socket, not when the broker
  receives it;
- with `retain`, it means the broker stored the message, not that a subscriber received it.

MQTT reuses a message id after 65,535 publishes, so the table is keyed by `id`, not `mid`.
When a tracked message reuses a message id that is still waiting for its arrival, the older row is
closed as `unconfirmed`. A message published directly by a plugin is not tracked, so its arrival
can still be attributed to a row that is waiting with the same message id. This is rare and only
happens when the id counter wraps.

## Table schema

```sql
CREATE TABLE IF NOT EXISTS mqtt_message_tracker (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    mid INTEGER NOT NULL,
    dateTime INTEGER,
    sent_ts DOUBLE NOT NULL,
    arrived_ts DOUBLE,
    status VARCHAR(16) NOT NULL,
    unconfirmed_ts DOUBLE,
    topic VARCHAR(512) NOT NULL,
    qos INTEGER NOT NULL,
    retain INTEGER NOT NULL,
    rc INTEGER,
    payload MEDIUMTEXT
)
```

## Separate database

The tracker can write to a database of its own.
Add the database and binding to `weewx.conf`:

```ini
[Databases]
    [[message_tracker]]
        database_name = mqtt_message_tracker.sdb
        driver = weedb.sqlite
        SQLITE_ROOT = /var/lib/weewx

[DataBindings]
    [[message_tracker_binding]]
        database = message_tracker
```

The database is created if it does not exist, unless `create_database` is `false`.
If it is created, an empty database is made; the tracker then creates its table.

Then configure the plugin to use the binding:

```ini
[MQTTPublish]
    plugins = MQTTAggregateValues, MQTTConfigHA, MQTTArchiveValues, MQTTMessageTracker

[MQTTMessageTracker]
    plugin = user.mqttmessagetracker.MQTTMessageTracker
    enable = true
    data_binding = message_tracker_binding
```

## SQLite locking

The tracker writes from its own thread, in batches and short transactions.
The default SQLite `timeout` is 5 seconds.
If the database is busy, the batch is logged as an error and dropped; publishing is not blocked.
With a separate database, this contention is with other writers of that file, not with the weather archive.

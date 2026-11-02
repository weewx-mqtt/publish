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
The install adds a `message_tracker_binding`; see [Separate database](#separate-database).
Required; there is no default, so the tracker never writes to the weather database by accident.

### create_database

Whether to create the database if it does not exist.
Valid values: `true` or `false`
Default is `true`.

### table

The name of the table to create and write to.
Default is `mqtt_message_tracker`.

### retention

The default retention, in seconds, for topics that do not set their own.
Set to `0` to keep them forever.
Default is `604800` (7 days).

Rows with the `sent` or `unconfirmed` status are never pruned.
They may still be delivered, or can still be replayed, so they stay until deleted by hand:

```sql
DELETE FROM mqtt_message_tracker WHERE status IN ('sent', 'unconfirmed') AND sent_ts < ?
```

### prune_interval

How often, in seconds, to delete rows older than their retention.
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

### topics

The `[[topics]]` section lists the topics to track.
Only the topics listed here are tracked; a message published to any other topic is not recorded.
Required; when there is no enabled topic, the plugin logs an error and does nothing.

#### enable

Whether to track this topic.
Valid values are `true` or `false`.
Default is `true`.

#### retention

How long, in seconds, to keep this topic's rows.
Set to `0` to keep them forever.
Sent and unconfirmed rows are never pruned.
Default is the `retention` option above.

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

## What is tracked

Each message published to a tracked topic records a row.

- `id`: a unique id for the row.
- `mid`: the MQTT message id.
- `dateTime`: the WeeWX timestamp of the data.
- `sent_ts`: when the message was handed to paho.
- `arrived_ts`: when paho reported it published, `NULL` for anything that is not `acked`.
- `status`: what is known about the message, see below.
- `unconfirmed_ts`: when the tracker stopped waiting for the arrival, `NULL` unless the status is `unconfirmed`.
- `origin_id`: the id of the original publish when this row is a replay, `NULL` otherwise.
- `attempt`: the replay number when this row is a replay, `NULL` for the original publish.
- `clientid`: the client that made a replay, `NULL` for a publish by MQTTPublish.
- `topic`: the topic the message was published on.
- `qos`: the quality of service level used.
- `retain`: whether the message is retained.
- `rc`: the paho result code.
- `payload`: the payload that was sent.
- `payload_encoding`: `text` or `hex`, `NULL` when there is no payload.

The payload is stored as text; binary payloads are hex-encoded and marked with
`payload_encoding`. With MySQL, `MEDIUMTEXT` holds up to 16 MB; SQLite has no practical limit.
A larger payload makes the insert fail and the batch is logged and dropped.

A replay of a message is a copy of its row, with its own `mid`, `sent_ts`, `arrived_ts`, `status`
and `rc`. It keeps the original `topic`, `qos`, `retain`, `dateTime` and `payload`, and points at
the original with `origin_id` and `attempt`. The original row is not changed.

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
`failed` when paho refuses the publish. A `sent` row is not pruned, so one whose arrival never
arrives is kept until the tracker stops, which closes it as `unconfirmed`.

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
closed as `unconfirmed`. A message published directly by a plugin, or to a topic that is not
tracked, is not recorded, so its arrival can still be attributed to a row that is waiting with
the same message id. This is rare and only happens when the id counter wraps.

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
    origin_id VARCHAR(32),
    attempt INTEGER,
    clientid VARCHAR(128),
    topic VARCHAR(512) NOT NULL,
    qos INTEGER NOT NULL,
    retain INTEGER NOT NULL,
    rc INTEGER,
    payload MEDIUMTEXT,
    payload_encoding VARCHAR(8)
)
```

## Replaying a message

`failed` and `unconfirmed` rows can be republished with `bin/user/mqttreplay.py`.
It reads the tracker table and publishes through its own MQTT client; MQTTPublish is not
involved and does not record the replay as a new publish.

The tool is a dry run unless `--publish` is given:

```shell
python /usr/share/weewx/bin/user/mqttreplay.py /etc/weewx/weewx.conf
python /usr/share/weewx/bin/user/mqttreplay.py /etc/weewx/weewx.conf --publish
```

A replay is a new row, so the original is never changed:

| id | topic | status | origin_id | attempt |
| --- | --- | --- | --- | --- |
| A | weather/outTemp_F | unconfirmed | NULL | NULL |
| B | weather/outTemp_F | acked | A | 1 |

The replay copies the topic, QoS, retain flag, `dateTime` and payload of the original.
Its `origin_id` is the original row and `attempt` counts the replays of that message from 1.
Replaying a replay keeps the chain flat under the original, so that message's history is:

```sql
SELECT id, attempt, mid, sent_ts, arrived_ts, status, rc
FROM mqtt_message_tracker WHERE origin_id = ? ORDER BY attempt
```

The tool:

- selects `unconfirmed` rows. Use `--status failed`, or `failed,unconfirmed`, to include `failed`.
  A `sent` row may still be in flight and an `acked` row does not need a replay;
- only considers rows sent within `--since` seconds (default `3600`) and replays at most
  `--limit` messages (default `100`);
- replays only the newest row per topic, so an old value cannot overwrite a newer one.
  `--all` replays every selected message, oldest first;
- skips a message that already has an `acked` replay; `--force` overrides;
- filters the topics with `--topic`, a glob such as `weather/outTemp_*`;
- connects with a clientid of its own, so the running service is not disconnected;
- waits for the connection before publishing, and for each publish to be confirmed, with
  `--ack-timeout` (default `10` seconds).

Unconfirmed rows are never pruned, so the tool can select a message that is older than the
retention period.

`--plugin-section`, `--data-binding` and `--table` select a tracker that is configured under
another section or writes to another database.

A message published directly by a plugin, or to a topic that is not tracked, is never replayed.

The exit code is `0` on success, `1` when the connection, a publish or an ack failed, and `2` for
a config or database error. A connect failure stops the run before anything is published.

The write sequence matches the tracker: the replay is inserted as `sent` after paho accepts it,
then updated to `acked` or `unconfirmed`. A tool that is killed after publishing leaves a `sent`
row, which the tracker closes as `unconfirmed` the next time it starts.

Replay is not delivery: it cannot undo an earlier loss, and it may publish a duplicate.
It assumes the consumer is idempotent on `dateTime`, which is true for InfluxDB and typical
time-series stores.

## Separate database

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

## SQLite locking

The tracker writes from its own thread, in batches and short transactions.
The default SQLite `timeout` is 5 seconds.
If the database is busy, the batch is logged as an error and dropped; publishing is not blocked.
With a separate database, this contention is with other writers of that file, not with the weather archive.

---
title: MQTTMessageTracker
parent: Plugins
nav_order: 4
---
{% include messagetracker_warning.html %}

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

The default retention, in seconds, for `acked` and `failed` rows in topics that do not set their own.
Set to `0` to keep them forever.
Default is `604800` (7 days).

### unconfirmed_retention

How long, in seconds, to keep `unconfirmed` rows in topics that do not set their own.
Set to `0` to keep them forever.
Default is `0`.

A `sent` row is not pruned; the startup sweep marks it `unconfirmed`, which this option then bounds.
See [Pruning](#pruning) to remove them sooner.

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

### resend

The `[[resend]]` section controls automatic resending after a successful connection.
It is disabled by default.

```ini
[MQTTMessageTracker]
    [[resend]]
        enable = true
```

#### enable

Whether to resend messages after a successful connection.
Default is `false`.

#### on_startup

Whether to resend after the first successful connection of the tracker.
Default is `true`.

#### on_reconnect

Whether to resend after a reconnect.
Default is `true`.

#### include_before_last_success

Whether to resend every `unconfirmed` and `failed` message for a topic, including messages
older than that topic's last confirmed publish.
Default is `false`.

#### since

Only resend messages sent within the last `since` seconds.
Set to `0` to consider every message after the last confirmed publish.
Default is `0`.

#### limit

The maximum number of messages to resend per connection.
Set to `0` to resend every message.
Default is `0`.

### topics

The `[[topics]]` section lists the topics to track.
Only the topics listed here are tracked; a message published to any other topic is not recorded.
Required; when there is no enabled topic, the plugin logs an error and does nothing.

A topic published with `qos = 0` is rejected: a qos 0 message is never acknowledged, so its
delivery cannot be confirmed and the tracker could only record it as if it had been. The plugin
logs an error and does not track that topic.

#### enable

Whether to track this topic.
Valid values are `true` or `false`.
Default is `true`.

#### retention

How long, in seconds, to keep this topic's `acked` and `failed` rows.
Set to `0` to keep them forever.
Default is the `retention` option above.

#### unconfirmed_retention

How long, in seconds, to keep this topic's `unconfirmed` rows.
Set to `0` to keep them forever.
Default is the `unconfirmed_retention` option above.

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
- `origin_id`: the id of the original publish when this row is a resend, `NULL` otherwise.
- `attempt`: the resend number when this row is a resend, `NULL` for the original publish.
- `clientid`: the client that made a resend, `NULL` for the original publish.
- `topic`: the topic the message was published on.
- `qos`: the quality of service level used.
- `retain`: whether the message is retained.
- `rc`: the paho result code.
- `payload`: the payload that was sent.
- `payload_encoding`: `text` or `hex`, `NULL` when there is no payload.

The payload is stored as text; binary payloads are hex-encoded and marked with
`payload_encoding`. With MySQL, `MEDIUMTEXT` holds up to 16 MB; SQLite has no practical limit.
A larger payload makes the insert fail and the batch is logged and dropped.

A resend of a message is a copy of its row, with its own `mid`, `sent_ts`, `arrived_ts`, `status`
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
`failed` when paho refuses the publish. If the connection is lost, the rows in flight are marked
`unconfirmed`; otherwise a row whose arrival never arrives is kept until the tracker stops, which
marks it `unconfirmed`. `unconfirmed_retention` then bounds it.

`unconfirmed` does not mean the message was not delivered. It means the tracker cannot tell: paho
never reported the arrival, and no further report can arrive. That is why it is recorded as its own
status instead of an empty `arrived_ts`.

Rows are marked `unconfirmed`:

- when the connection is lost and paho has not reported the arrival, with `unconfirmed_ts` set
  to the disconnect time. No arrival can be reported for a message that was in flight when the
  connection went away;
- when the publishing thread stops and paho has not reported the arrival, with `unconfirmed_ts`
  set to the shutdown time. This includes messages that were delivered but whose arrival was not
  reported before the process stopped;
- when paho reuses a message id before the arrival of the older message is reported, with
  `unconfirmed_ts` set to the time of the reuse;
- at startup, for the rows a previous run left in `sent`, with `unconfirmed_ts` set to the startup
  time. This covers a process that stopped without shutting down cleanly. The sweep logs how many
  rows it marked, so a shutdown that did not complete is visible in the log.

An `acked` row is also not proof of delivery to a subscriber:

- with QoS 0, paho reports the message once it is written to the socket, not when the broker
  receives it;
- with `retain`, it means the broker stored the message, not that a subscriber received it.

MQTT reuses a message id after 65,535 publishes, so the table is keyed by `id`, not `mid`.
When a tracked message reuses a message id that is still waiting for its arrival, the older row is
marked `unconfirmed`. A message published directly by a plugin, or to a topic that is not
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

## Resending automatically

When `[[resend]]` is enabled, the tracker resends messages after a successful connection,
including a reconnect. It resends the messages after the last confirmed publish on each topic:

- the last confirmed publish is the newest original row that is `acked`, or whose resend is
  `acked`. A resend's own time does not move the boundary, otherwise a successful resend could
  hide an older backlog;
- every `failed` and `unconfirmed` row after that boundary is resent, oldest first;
- if a topic has no confirmed publish, every `failed` and `unconfirmed` row is resent;
- with `include_before_last_success = true`, the boundary is ignored and every `failed` and
  `unconfirmed` row for the topic is resent, even those before the last confirmed publish;
- a message is resent once, even when it already has several resend attempts.

The boundary is per topic. A successful publish on one topic says nothing about the delivery of
another topic.

The resend runs on the tracker's writer thread, so it does not block paho's network loop and
does not open a second MQTT or database connection. It publishes each message and records a new
resend row, then waits for the normal `on_publish` callback to mark it `acked`. A message that was
in flight when the connection was lost is marked `unconfirmed` by the `on_disconnect` callback, so
it is part of the next resend.

`since` limits the age of the rows considered, and `limit` caps a run. Set `limit` to `0` to
resend every message. A capped run resends the oldest messages first, but a later live publish
can move the boundary past the remaining backlog; the manual tool is the way to clear an old
backlog without that risk.

Automatic resend is best-effort. A live publish that races the resend can still land after an
older resent value; consumers are assumed to be idempotent on `dateTime`.
See [QoS and duplicate delivery](#qos-and-duplicate-delivery).

## Resending a message

`failed` and `unconfirmed` rows can also be resent with `bin/user/mqttresend.py`.
It reads the tracker table and publishes through its own MQTT client; MQTTPublish is not
involved and does not record the resend as a new publish.

The tool is a dry run unless `--publish` is given:

```shell
python /usr/share/weewx/bin/user/mqttresend.py /etc/weewx/weewx.conf
python /usr/share/weewx/bin/user/mqttresend.py /etc/weewx/weewx.conf --publish
```

The tools import WeeWX, so run them with the Python that WeeWX uses and with WeeWX on the
path. A package install already has it there. For a source install, add its `src` directory:

```shell
PYTHONPATH=~/weewx/src python ~/weewx-data/bin/user/mqttresend.py ~/weewx-data/weewx.conf
```

A resend is a new row, so the original is never changed:

| id | topic | status | origin_id | attempt |
| --- | --- | --- | --- | --- |
| A | weather/outTemp_F | unconfirmed | NULL | NULL |
| B | weather/outTemp_F | acked | A | 1 |

The resend copies the topic, QoS, retain flag, `dateTime` and payload of the original.
Its `origin_id` is the original row and `attempt` counts the resends of that message from 1.
Resending a resend keeps the chain flat under the original, so that message's history is:

```sql
SELECT id, attempt, mid, sent_ts, arrived_ts, status, rc
FROM mqtt_message_tracker WHERE origin_id = ? ORDER BY attempt
```

The tool:

- selects `unconfirmed` rows. Use `--status failed`, or `failed,unconfirmed`, to include `failed`.
  A `sent` row may still be in flight and an `acked` row does not need a resend;
- considers every `unconfirmed` message, whatever its age; `--since SECONDS` bounds it, and
  `--limit` caps the number resent (default `100`);
- resends only the newest row per topic, so an old value cannot overwrite a newer one. A message
  this hides is reported, and `--all` resends every selected message, oldest first;
- skips a message that already has an `acked` resend; `--force` overrides;
- filters the topics with `--topic`, a glob such as `weather/outTemp_*`;
- connects with a clientid of its own, so the running service is not disconnected;
- waits for the connection before publishing, and for each publish to be confirmed, with
  `--ack-timeout` (default `10` seconds).

Unconfirmed rows are kept until `unconfirmed_retention` (default never), so the tool can select a
message that is older than the normal retention period.

`--plugin-section`, `--data-binding` and `--table` select a tracker that is configured under
another section or writes to another database.

A message published directly by a plugin, or to a topic that is not tracked, is never resent.

The exit code is `0` on success, `1` when the connection, a publish or an ack failed, and `2` for
a config or database error. A connect failure stops the run before anything is published.

The write sequence matches the tracker: the resend is inserted as `sent` after paho accepts it,
then updated to `acked` or `unconfirmed`. A tool that is killed after publishing leaves a `sent`
row, which the tracker marks `unconfirmed` the next time it starts.

Resend is not delivery: it cannot undo an earlier loss, and it may publish a duplicate.
It assumes the consumer is idempotent on `dateTime`, which is true for InfluxDB and typical
time-series stores.

## QoS and duplicate delivery

QoS 2 is exactly-once for a single publish within a single MQTT session. It is not an end-to-end
guarantee across reconnects, restarts, or application retries.

A resend is a new publish with a new packet id. The broker cannot tell that it is a replay, so a
subscriber can receive the same application message more than once, even when the topic uses
QoS 2. This applies to both automatic resend and `mqttresend.py`.

The tracker therefore provides at-least-once delivery end to end. Consumers must be idempotent,
for example by deduplicating on `dateTime`. `failed` rows are safe to resend: paho refused them,
so they were not published. `unconfirmed` rows are the ambiguous ones: the original may have
reached the broker, but its acknowledgement was not observed.

## Pruning

The tracker prunes `acked` and `failed` rows by age, using each topic's `retention` (or the
plugin-level `retention` for topics that are no longer configured). `unconfirmed` rows are pruned
by `unconfirmed_retention`, which defaults to `0` (never). `sent` rows are not pruned; the startup
sweep marks them `unconfirmed`.

To remove unconfirmed rows sooner, or when `unconfirmed_retention` is `0`, run
`bin/user/mqttprune.py`:

```shell
python /usr/share/weewx/bin/user/mqttprune.py /etc/weewx/weewx.conf
python /usr/share/weewx/bin/user/mqttprune.py /etc/weewx/weewx.conf --delete
```

Without `--delete` it only prints the selection.

By default a row is selected when it is older than its topic's `retention` — the age the normal
policy uses. Use `--older-than` to match `unconfirmed_retention`, or to prune sooner.
`--older-than 0` selects every matching row, including topics whose retention is `0`.

- `--status unconfirmed` is the default. Use `--status failed`, or `failed,unconfirmed`, to
  include `failed`. `sent` is refused (it may be in flight; restart WeeWX to mark it
  `unconfirmed`) and `acked` is refused (the automatic prune handles it).
- `--topic` filters with a glob, and `--limit` caps the run (default `100`, oldest first).
- `--plugin-section`, `--data-binding` and `--table` select a tracker configured elsewhere.

The tool deletes by id and status, so a row that changed between the plan and the delete is left
alone. It is safe to run while WeeWX is running.

Deleting an `unconfirmed` row discards the only record that its delivery outcome is unknown.
Deleting an original row while an `acked` resend remains leaves that resend's `origin_id`
pointing at a row that no longer exists; the resend row is self-contained, so it still resends
and prunes normally.

A `sent` row is marked `unconfirmed` when the tracker restarts, so the tool does not touch it.
If the tool is not installed, the same can be done with SQL:

```sql
DELETE FROM mqtt_message_tracker WHERE status = 'unconfirmed' AND sent_ts < ?
```

### Scheduling

`unconfirmed_retention` bounds unconfirmed rows automatically. Use the tool on a timer when you
want a different age or cadence, want to prune `failed` early, or leave `unconfirmed_retention`
at `0`.

Run it once without `--delete` first, to see the selection.

A system cron entry in `/etc/cron.d/mqttprune`:

```cron
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Every day at 03:15, delete unconfirmed rows older than their topic's retention.
15 3 * * * weewx /usr/bin/python3 /usr/share/weewx/bin/user/mqttprune.py /etc/weewx/weewx.conf --delete >> /var/log/weewx/mqttprune.log 2>&1
```

The same line in the WeeWX user's crontab (`crontab -u weewx -e`) drops the user field:

```cron
15 3 * * * /usr/bin/python3 /usr/share/weewx/bin/user/mqttprune.py /etc/weewx/weewx.conf --delete >> /var/log/weewx/mqttprune.log 2>&1
```

To clear a backlog after an outage, widen the age, include `failed`, and raise the limit:

```cron
15 3 * * * weewx /usr/bin/python3 /usr/share/weewx/bin/user/mqttprune.py /etc/weewx/weewx.conf --status unconfirmed,failed --older-than 2592000 --limit 1000 --delete >> /var/log/weewx/mqttprune.log 2>&1
```

- Run as the WeeWX user, not root, so the database permissions match.
- Use the Python that WeeWX uses.
- `--delete` is required; without it the tool is a dry run.
- `--limit` defaults to `100`, so a large backlog clears over several runs. `--limit 0` removes
  the limit.
- The tool is safe while WeeWX is running.
- The exit code is `0` on success and `2` on a config or database error. Cron only sends mail
  when the command writes output, so keep the log and rotate it, or leave stderr unredirected
  with `MAILTO` set. The log directory must exist and be writable by the WeeWX user; `logger -t
  mqttprune` can be used instead of a file.

A systemd timer is an alternative to cron. For example,
`/etc/systemd/system/mqttprune.service`:

```ini
[Unit]
Description=Prune the MQTT message tracker

[Service]
Type=oneshot
User=weewx
ExecStart=/usr/bin/python3 /usr/share/weewx/bin/user/mqttprune.py /etc/weewx/weewx.conf --delete
```

and `/etc/systemd/system/mqttprune.timer`:

```ini
[Unit]
Description=Run the MQTT message tracker prune daily

[Timer]
OnCalendar=*-*-* 03:15:00
Persistent=true

[Install]
WantedBy=timers.target
```

Then enable it with `systemctl daemon-reload` and `systemctl enable --now mqttprune.timer`.
The service's output goes to the journal.

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

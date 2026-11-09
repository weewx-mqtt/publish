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

An `acked` row is a record of what paho reported as published. Pruning it frees space but loses
that history. A `failed` row can still be resent, so pruning it removes a message that could
otherwise have been recovered. `retention` does not apply to `unconfirmed` rows.

### unconfirmed_retention

How long, in seconds, to keep `unconfirmed` rows in topics that do not set their own.
Set to `0` to keep them forever.
Default is `0`.

`unconfirmed` rows are the ones a resend can still recover. Keeping them forever preserves the
whole recovery window, but the table can grow after an outage. A finite value bounds the table at
the cost of losing older messages before they are resent. This option does not apply to `acked` or
`failed` rows.

A `sent` row is not pruned; the startup sweep and a disconnect mark it `unconfirmed`, which this
option then bounds. See [Pruning](#pruning) to remove them sooner.

### prune_interval

How often, in seconds, to delete rows older than their retention.
Default is `3600`.

### Advanced options

These control the tracker's writer thread. The defaults are suitable for normal use.
See [Internals](internals/index.md) for the implementation details.

#### queue_size

The maximum number of events to queue before they are dropped.
The queue is drained by a background thread.
Default is `10000`.

#### batch_size

The maximum number of events written in one transaction.
Default is `100`.

#### pending_ttl

How long, in seconds, to keep an arrival that arrived before its send event.
This can happen because the MQTT callback and the publishing code run on different threads.
Default is `60`.

#### shutdown_timeout

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
| `acked` | paho reported the message as published; `arrived_ts` is set. |
| `unconfirmed` | no arrival was reported before the tracker stopped waiting; `unconfirmed_ts` is set. |

`sent` is transient: it moves to `acked` when paho reports the publish, or to `failed` when paho
refuses it. `unconfirmed` is not proof that the message was not delivered; it means the tracker
could not tell.

An `acked` row is not proof a subscriber received it: with QoS 0 paho reports the message once it
is written to the socket, and with `retain` it means the broker stored it. See
[QoS and duplicate delivery](#qos-and-duplicate-delivery).

See [Internals](internals/index.md#status-lifecycle) for when rows are marked `unconfirmed`, and
for the message-id reuse behavior.

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

The resend uses the tracker's existing MQTT connection. It publishes each message and records a
new resend row; a later `on_publish` marks the row `acked`. A message that was in flight when the
connection was lost is marked `unconfirmed`, so it is part of the next resend.

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

A resend is a new row, so the original is never changed. It copies the topic, QoS, retain flag,
`dateTime` and payload of the original, and points at the original with `origin_id` and `attempt`.
See [Internals](internals/index.md#resend-rows) for the row layout and history query.

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

A tool that is killed after publishing leaves a `sent` row, which the tracker marks `unconfirmed`
the next time it starts. See [Internals](internals/index.md#resend-rows) for the write sequence.

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

The retentions decide how long a message remains available to resend. `retention` bounds `acked`
and `failed` rows; `unconfirmed_retention` bounds the uncertain rows a resend can still use.
Shortening either makes older messages unrecoverable; keeping them at `0` preserves recovery but
lets the table grow.

The tracker prunes `acked` and `failed` rows by age, using each topic's `retention` (or the
plugin-level `retention` for topics that are no longer configured). `unconfirmed` rows are pruned
by `unconfirmed_retention`, which defaults to `0` (never). `sent` rows are not pruned; the startup
sweep and a disconnect mark them `unconfirmed`.

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
See [Internals](internals/index.md#maintenance-sql) for the equivalent SQL.

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

The same line in the WeeWX user's crontab (`crontab -u weewx -e`) drops the `weewx` user field.

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

## Technical details

See [Internals](internals/index.md) for the table schema, status lifecycle, resend write sequence,
maintenance SQL, and SQLite locking.

---
title: Resending messages
parent: MQTTMessageTracker
ancestor: MQTTMessageTracker
nav_order: 2
---
{% include messagetracker_warning.html %}

A message that paho refused, or whose acknowledgement was never observed, can be published again.
The tracker can do it automatically after a connection, or you can run `mqttresend.py` yourself.

## Automatic resend

When `[[resend]]` is enabled, the tracker resends messages after a successful connection,
including a reconnect. It resends the messages after the last confirmed publish on each topic:

- the last confirmed publish is the newest original row that is `confirmed`, or whose resend is
  `confirmed`. A resend's own time does not move the boundary, otherwise a successful resend could
  hide an older backlog;
- every `failed` and `unconfirmed` row after that boundary is resent, oldest first;
- if a topic has no confirmed publish, every `failed` and `unconfirmed` row is resent;
- with `include_before_last_success = true`, the boundary is ignored and every `failed` and
  `unconfirmed` row for the topic is resent, even those before the last confirmed publish;
- a message is resent once, even when it already has several resend attempts.

The boundary is per topic. A successful publish on one topic says nothing about the delivery of
another topic.

The resend uses the tracker's existing MQTT connection. It publishes each message and records a
new resend row; a later `on_publish` marks the row `confirmed`. A message that was in flight when the
connection was lost is marked `unconfirmed`, so it is part of the next resend.

`since` limits the age of the rows considered, and `limit` caps a run. Set `limit` to `0` to
resend every message. A capped run resends the oldest messages first, but a later live publish
can move the boundary past the remaining backlog; the manual tool is the way to clear an old
backlog without that risk.

Automatic resend is best-effort. A live publish that races the resend can still land after an
older resent value; consumers are assumed to be idempotent on `dateTime`.
See [QoS and duplicate delivery](#qos-and-duplicate-delivery).

The `[[resend]]` options are in [Configuration](../configuration/resend/index.md).

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

## Resending with mqttresend.py

`failed` and `unconfirmed` rows can also be resent with `bin/user/mqttresend.py`.
It reads the tracker table and publishes through its own MQTT client; MQTTPublish is not
involved and does not record the resend as a new publish.

The tool is a dry run unless `--publish` is given:

```shell
python /usr/share/weewx/bin/user/mqttresend.py /etc/weewx/weewx.conf
python /usr/share/weewx/bin/user/mqttresend.py /etc/weewx/weewx.conf --publish
```

The tool imports WeeWX, so run it with the Python that WeeWX uses and with WeeWX on the path.
A package install already has it there. For a source install, add its `src` directory:

```shell
PYTHONPATH=~/weewx/src python ~/weewx-data/bin/user/mqttresend.py ~/weewx-data/weewx.conf
```

A resend is a new row, so the original is never changed. It copies the topic, QoS, retain flag,
`dateTime` and payload of the original, and points at the original with `origin_id` and `attempt`.
See [Internals](../internals/index.md#resend-rows) for the row layout and history query.

The tool:

- selects `unconfirmed` rows. Use `--status failed`, or `failed,unconfirmed`, to include `failed`.
  A `sent` row may still be in flight and a `confirmed` row does not need a resend;
- considers every `unconfirmed` message, whatever its age; `--since SECONDS` bounds it, and
  `--limit` caps the number resent (default `100`);
- resends only the newest row per topic, so an old value cannot overwrite a newer one. A message
  this hides is reported, and `--all` resends every selected message, oldest first;
- skips a message that already has a `confirmed` resend; `--force` overrides;
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
the next time it starts. See [Internals](../internals/index.md#resend-rows) for the write sequence.

Resend is not delivery: it cannot undo an earlier loss, and it may publish a duplicate.
It assumes the consumer is idempotent on `dateTime`, which is true for InfluxDB and typical
time-series stores.

---
title: Resending messages
parent: MQTTMessageTracker
ancestor: MQTTMessageTracker
nav_order: 2
---
{% include messagetracker_warning.html %}

A message that paho refused, or whose acknowledgement was never observed, can be published again.
The tracker can do it automatically after a connection, or you can run `mqttresend.py` yourself.

## What gets resent

Both automatic resend and `mqttresend.py` start from the tracker's `failed` and `unconfirmed`
rows. Automatic resend applies these rules:

- the last confirmed publish on a topic is the newest original row that is `confirmed`, or whose
  resend is `confirmed`. A resend's own time does not move the boundary, otherwise a successful
  resend could hide an older backlog;
- every `failed` and `unconfirmed` row after that boundary is resent, oldest first;
- if a topic has no confirmed publish, every `failed` and `unconfirmed` row is resent;
- with `include_before_last_success = true`, the boundary is ignored and every `failed` and
  `unconfirmed` row for the topic is resent, even those before the last confirmed publish;
- a message is resent once, even when it already has several resend attempts.

The boundary is per topic. A successful publish on one topic says nothing about the delivery of
another topic.

## Automatic resend

Automatic resend is configured in the `[[resend]]` section. It has two triggers, and both default
to `false`, so the section does nothing until one of them is `true`.

```ini
[MQTTMessageTracker]
    [[resend]]
        on_startup = true
        on_reconnect = true
```

### on_startup

Resend after the tracker's first successful connection after WeeWX starts.
Default is `false`.

Use it for the backlog left by the previous run. It fires once per WeeWX start, not on every
reconnect.

### on_reconnect

Resend after every later successful connection.
Default is `false`.

Use it for a connection lost while WeeWX is running. If `on_startup` is `false` and this is `true`,
the first connection is skipped and the next successful connection triggers the resend.

Setting both to `false` turns automatic resend off, the same as omitting the section.

### include_before_last_success

Whether to resend rows older than the topic's last confirmed publish.
Default is `false`.

By default the last confirmed publish is a boundary: an older message is assumed to have been
superseded, and is not resent. Set this to `true` to treat every `failed` and `unconfirmed` row as
a candidate, which is useful when the backlog is more important than the newer value.

### since

Only consider rows sent within the last `since` seconds.
Default is `0`, which applies no age limit.

The age is measured from the original message's `sent_ts`, not from the resend. Use this to avoid
republishing a very old value after a long outage.

### limit

The maximum number of messages to resend per connection.
Default is `0`, which resends every selected message.

A capped run resends the oldest messages first. A later live publish can move the boundary past
the remaining backlog, so use `mqttresend.py` to clear an old backlog without that risk.

The full option and default reference is in
[Configuration](../configuration/resend/index.md).

## What a resend does

The tracker resends through its existing MQTT connection. It publishes each message and records a
new resend row; a later `on_publish` marks the row `confirmed`. A message that was in flight when
the connection was lost is marked `unconfirmed`, so it is part of the next resend.

Automatic resend is best-effort. A live publish that races the resend can still land after an
older resent value; consumers are assumed to be idempotent on `dateTime`.
See [QoS and duplicate delivery](../index.md#qos-and-duplicate-delivery).

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

### What the tool selects

By default the tool selects `unconfirmed` rows, whatever their age. It then:

- resends only the newest row per topic, so an old value cannot overwrite a newer one; a message
  this hides is reported, and `--all` resends every selected message, oldest first;
- skips a message that already has a `confirmed` resend; `--force` overrides;
- connects with a clientid of its own, so the running service is not disconnected;
- waits for the connection before publishing, and for each publish to be confirmed.

A resend is a new row, so the original is never changed. It copies the topic, QoS, retain flag,
`dateTime` and payload of the original, and points at the original with `origin_id` and `attempt`.
See [Internals](../internals/index.md#resend-rows) for the row layout and history query.

A row can only be resent while the tracker has not pruned it, so the topic's `error_retention` sets
the recovery window. Keep it long enough to cover the outages you want to recover from.

A message published directly by a plugin, or to a topic that is not tracked, is never resent.

The exit code is `0` on success, `1` when the connection, a publish or an ack failed, and `2` for
a config or database error. A connect failure stops the run before anything is published.

A tool that is killed after publishing leaves a `sent` row, which the tracker marks `unconfirmed`
the next time it starts. See [Internals](../internals/index.md#resend-rows) for the write sequence.

Resend is not delivery: it cannot undo an earlier loss, and it may publish a duplicate.
It assumes the consumer is idempotent on `dateTime`, which is true for InfluxDB and typical
time-series stores.

## mqttresend.py options

The first argument is the WeeWX config file. The rest are options.

### --publish

Publish the selection. Without it the tool is a dry run: it prints what it would resend and sends
nothing.

### --status STATUS

A comma-separated list of statuses to resend.
Default is `unconfirmed`.

Use `--status failed` to resend only failed publishes, or `--status failed,unconfirmed` for both.
`sent` may still be in flight and `confirmed` does not need a resend, so both are refused.

```shell
python /usr/share/weewx/bin/user/mqttresend.py /etc/weewx/weewx.conf \
    --status failed,unconfirmed --publish
```

### --since SECONDS

Only resend messages sent within the last `SECONDS`.
Default is every message, whatever its age.

The age is measured from the original's `sent_ts`, not from the resend. Use it together with
`error_retention` to bound an old backlog.

### --limit COUNT

The maximum number of messages to resend.
Default is `100`; `0` removes the limit.

The selection is resent oldest first.

### --topic GLOB

Only resend topics that match the glob.

```shell
python /usr/share/weewx/bin/user/mqttresend.py /etc/weewx/weewx.conf \
    --topic 'weather/outTemp_*' --publish
```

### --all

Resend every selected message, not just the newest row per topic.

By default only the newest message per topic is resent, so an old value cannot overwrite a newer
one. A message this hides is reported; `--all` is how you publish it too, oldest first.

### --force

Resend messages that already have a `confirmed` resend.

The tool skips them by default because they were already delivered once. Use `--force` when you
need another copy despite that.

### --ack-timeout SECONDS

How long to wait for each publish to be acknowledged.
Default is `10`.

If the wait expires, that resend row is marked `unconfirmed` and the run exits `1`. The other
selected messages are still attempted.

### --connect-timeout SECONDS

How long to wait for the connection before giving up.
Default is `10`.

A connect failure stops the run before anything is published.

### --clientid ID

The clientid to connect with.
Default is a unique id starting with `MQTTPublish-resend`, so the tool does not disconnect the
running service.

### --plugin-section NAME

The tracker's config section.
Default is `MQTTMessageTracker`.

### --data-binding NAME

Override the tracker's `data_binding` option.

### --table NAME

Override the tracker's `table` option.

### --version

Print the tool's version and exit.

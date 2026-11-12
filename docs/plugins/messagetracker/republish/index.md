---
title: Republishing messages
parent: MQTTMessageTracker
ancestor: MQTTMessageTracker
nav_order: 2
---
{% include messagetracker_warning.html %}

A message that paho refused, or whose acknowledgement was never observed, can be published again.
The tracker can do it automatically after a connection, or you can run `mqtttracker republish`
yourself.

## What gets republished

A message that was not delivered can be republished. A message is delivered when its outcome is
`confirmed` (see [Status](../status/index.md)); a delivered message is not republished unless you
ask for it. Each message is republished once, even when it already has several attempts.

`mqtttracker republish` starts from the unresolved messages and, by default, republishes only the
newest one on each topic, so an old value cannot overwrite a newer one. `--all` republishes every
unresolved message, subject to the tool's other options.

Automatic republishing uses the last delivered message on each topic as a boundary instead. It
republishes every unresolved message published after it, not just the newest.

The last delivered message on a topic is the newest original message that is `confirmed`, either
directly or through a republish attempt. A confirmed republish attempt does not update that point
in time; otherwise, republishing an old message could hide a newer unresolved one.

So automatic republishing:

- republishes every unresolved message published after the last delivered message on its topic,
  oldest first;
- republishes every unresolved message on a topic with no delivered message;
- with `include_before_last_success = true`, ignores the last delivered message and republishes
  every unresolved message.

The last delivered message is per topic: a publish on one topic says nothing about another.

`mqtttracker republish` does not use that boundary; see
[What the tool selects](#what-the-tool-selects).

## Automatic republishing

Automatic republishing is configured in the `[[republish]]` section. It has two triggers, and both
default to `false`, so the section does nothing until one of them is `true`.

```ini
[MQTTMessageTracker]
    [[republish]]
        on_startup = true
        on_reconnect = true
```

### on_startup

Republish after the tracker's first successful connection after WeeWX starts.
Default is `false`.

Use it for the backlog left by the previous run. It fires once per WeeWX start, not on every
reconnect.

### on_reconnect

Republish after every later successful connection.
Default is `false`.

Use it for a connection lost while WeeWX is running. If `on_startup` is `false` and this is `true`,
the first connection is skipped and the next successful connection triggers the republish.

Setting both to `false` turns automatic republishing off, the same as omitting the section.

The log records each connection: `Startup republish requested after the first connection.` or
`Republish requested after a reconnect.` when a republish is queued, and
`No messages need to be republished after the connection was established.` when there is nothing
to select. A trigger that is off is logged at `DEBUG`.

### include_before_last_success

Whether to republish messages older than the topic's last delivered message.
Default is `false`.

By default, an older message is assumed to have been superseded and is not republished. Set this
to `true` to treat every unresolved message as a candidate, which is useful when the backlog is
more important than the newer value.

### since

Only consider messages published within the last `since` seconds.
Default is `0`, which applies no age limit.

The age is measured from the original message's `published_ts`, not from a republish attempt. Use this
to avoid republishing a very old value after a long outage.

### limit

The maximum number of messages to republish per connection.
Default is `0`, which republishes every selected message.

A capped run republishes the oldest messages first. A later live publish can move the boundary past
the remaining backlog, so use `mqtttracker republish` to clear an old backlog without that risk.

The full option and default reference is in
[Configuration](../configuration/republish/index.md).

## What republishing does

The tracker republishes through its existing MQTT connection. It publishes each message and records
a new attempt; a later `on_publish` marks it `confirmed`. A message that was in flight when the
connection was lost is marked `unconfirmed`, so it is part of the next republish.

Automatic republishing is best-effort. A live publish that races the republish can still land after
an older republished value; consumers are assumed to be idempotent on `dateTime`.
See [QoS and duplicate delivery](../index.md#qos-and-duplicate-delivery).

## Republishing with mqtttracker republish

`failed` and `unconfirmed` messages can also be republished with `bin/user/mqtttracker.py republish`.
It reads the tracker table and publishes through its own MQTT client; MQTTPublish is not
involved and does not record it as a new publish.

`mqtttracker` is one tool with three subcommands: `republish`, `prune` and `status`. The config
file is a global `--config` option, so it comes before the subcommand.

The tool is in the tracker's user directory: `/etc/weewx/bin/user` on a package install (apt,
rpm, openSUSE) and `~/weewx-data/bin/user` on a pip or git install. Run it with the Python that
WeeWX uses.

`republish` is a dry run unless `--publish` is given:

```shell
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf republish
```

Publish the selection:

```shell
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf republish --publish
```

On a package install the tool finds WeeWX by itself; for an uninstalled source checkout, add
WeeWX's `src` directory to `PYTHONPATH`:

```shell
PYTHONPATH=~/weewx/src python3 ~/weewx-data/bin/user/mqtttracker.py --config ~/weewx-data/weewx.conf republish
```

### What the tool selects

By default the tool selects the messages whose outcome is `failed` or `unconfirmed`, whatever
their age. It then:

- republishes only the newest message per topic, so an old value cannot overwrite a newer one; a
  message this hides is reported, and `--all` republishes every selected message, oldest first;
- skips a message that is already delivered (one attempt is `confirmed`); `--force` overrides;
- connects with a clientid of its own, so the running service is not disconnected;
- waits for the connection before publishing, and for each publish to be confirmed.

Republishing never changes the original message. It publishes the same topic, QoS, retain flag,
`dateTime` and payload again.
See [Internals](../internals/index.md#republish-rows) for the stored layout and history query.

A message can only be republished while the tracker has not pruned it, so the topic's
`error_retention` sets the recovery window for an unresolved message. Keep it long enough to cover
the outages you want to recover from.

A message published directly by a plugin, or to a topic that is not tracked, is never republished.

The exit code is `0` on success, `1` when the connection, a publish or an ack failed, and `2` for
a config or database error. A connect failure stops the run before anything is published.

A tool that is killed after publishing leaves the message `inflight`, which the tracker marks
`unconfirmed`
the next time it starts. See [Internals](../internals/index.md#republish-rows) for the write
sequence.

Republishing is not delivery: it cannot undo an earlier loss, and it may publish a duplicate.
It assumes the consumer is idempotent on `dateTime`, which is true for InfluxDB and typical
time-series stores.

## republish options

The first argument is the WeeWX config file. The rest are options.

### --publish

Publish the selection. Without it the tool is a dry run: it prints what it would republish and
publishes nothing.

### --status STATUS

A comma-separated list of message statuses to republish.
Default is `failed,unconfirmed`.

Use `--status unconfirmed` to republish only the ambiguous messages, or `--status failed` to
republish only failed publishes. `inflight` may still be in flight and `confirmed` does not need to be
republished, so both are refused.

```shell
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf republish --status unconfirmed --publish
```

### --since SECONDS

Only republish messages whose outcome is within the last `SECONDS`.
Default is every message, whatever its age.

The age is measured from the message's latest attempt, which is the original publish or a
republish attempt. Use it together with `error_retention` to bound an old backlog.

### --limit COUNT

The maximum number of messages to republish.
Default is `100`; `0` removes the limit.

The selection is republished oldest first.

### --topic GLOB

Only republish topics that match the glob.

```shell
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf republish --topic 'weather/outTemp_*' --publish
```

### --all

Republish every selected message, not just the newest message per topic.

By default only the newest message per topic is republished, so an old value cannot overwrite a
newer one. A message this hides is reported; `--all` is how you publish it too, oldest first.

### --force

Republish messages that are already delivered (they have a `confirmed` attempt).

The tool skips them by default because they were already delivered once. Use `--force` when you
need another copy despite that.

### --ack-timeout SECONDS

How long to wait for each publish to be acknowledged.
Default is `10`.

If the wait expires, that message is marked `unconfirmed` and the run exits `1`. The other
selected messages are still attempted.

### --connect-timeout SECONDS

How long to wait for the connection before giving up.
Default is `10`.

A connect failure stops the run before anything is published.

### --clientid ID

The clientid to connect with.
Default is a unique id starting with `MQTTPublish-republish`, so the tool does not disconnect the
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

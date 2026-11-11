---
title: Status
parent: MQTTMessageTracker
ancestor: MQTTMessageTracker
nav_order: 4
---
{% include messagetracker_warning.html %}

`mqtttracker status` shows one line per tracked message, with the status the tracker has
recorded for it. The tracker stores a chain of rows for each message: the original publish, then
one row per republish attempt. The message's status is the status of its outcome row — the latest
confirmed attempt if there is one, otherwise the latest attempt. By default it shows the
unresolved messages: those whose status is `failed`, `unconfirmed`, or `inflight`. `--status` chooses
the statuses to show. It reads the tracker database directly, so it does not need MQTTPublish to
be running.

`mqtttracker` is one tool with `republish`, `prune` and `status` subcommands. The config file is a
global `--config` option, so it comes before the subcommand. Show the unresolved messages:

```shell
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf status
```

Show the delivered history:

```shell
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf status --status confirmed
```

Show the messages still in flight:

```shell
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf status --status inflight
```

Show one message chain:

```shell
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf status --message 3f2a9c...
```

The tool is in the tracker's user directory: `/etc/weewx/bin/user` on a package install (apt,
rpm, openSUSE) and `~/weewx-data/bin/user` on a pip or git install. Run it with the Python that
WeeWX uses. On a package install it finds WeeWX by itself; for an uninstalled source checkout,
add WeeWX's `src` directory to `PYTHONPATH`:

```shell
PYTHONPATH=~/weewx/src python3 ~/weewx-data/bin/user/mqtttracker.py --config ~/weewx-data/weewx.conf status
```

## Reading the result

The original row is never changed; each republish attempt records its own outcome. A message is
**confirmed** when any attempt was confirmed. A confirmed attempt wins, so a delivered message is
never counted as failed again, even after a forced republish. "Confirmed" means the broker accepted
the publish, not that a subscriber received it.

A message with several republish attempts appears once. The row is anchored at the original, or at
the oldest surviving attempt when the original was pruned. `ATTEMPTS`, `CONFIRMED`, and
`CURRENT STATUS` summarize the rest of the chain.

The default summary lists each message with:

| column | meaning |
| --- | --- |
| `ID` | the anchor row id; `--message` also accepts a republish attempt id. |
| `TOPIC` | the topic the message was published on. |
| `ORIGINAL STATUS` | the anchor row's status: `failed`, `unconfirmed`, `inflight`, or `confirmed`. |
| `ORIGINALLY PUBLISHED` | when the anchor was handed to paho. |
| `ATTEMPTS` | the number of republish attempts in the chain, whatever their status. |
| `CONFIRMED` | how many of those attempts the broker confirmed. |
| `CURRENT STATUS` | the outcome: `confirmed`, `failed`, `unconfirmed`, or `inflight`. |

The outcomes mean:

- `confirmed`: delivered — the broker accepted at least one attempt;
- `failed` or `unconfirmed`: the latest attempt failed, or its outcome is unknown;
- `inflight`: an attempt is in flight.

## Options

### --status STATUS

The statuses to show, comma separated.
Default is `failed,unconfirmed,inflight`. Choose from `failed`, `unconfirmed`, `inflight`, and `confirmed`.
This filters the message's current status, so a delivered message does not appear under
`--status failed` just because its original row failed.

`inflight` messages are in flight: paho accepted the publish, but no acknowledgement has arrived yet.
They become `confirmed` on acknowledgement, or `unconfirmed` on a disconnect or the startup sweep.
`confirmed` messages are success history and can be numerous; `--status confirmed` shows them.

### --message ID

Show one message chain, in publish order.

Use any row id from the chain, including a republish attempt id. The command resolves it to the
chain and shows the anchor and each republish attempt, with its `attempt` and `origin_id`. If no
row has that id, the command prints a message and exits `1`. The plan prints the id as `id=<hex>`;
either that form or the bare id is accepted.

### --topic GLOB

Only show messages whose topic matches the glob, for example `weather/outTemp_*`.

### --limit COUNT

The maximum number of messages to show.
Default is `100`; `0` shows every message.

## The same information in SQL

These queries show the underlying rows. They are useful when the tool is not installed, or for a
monitor that queries the database directly.

For one message, starting from the id in the log:

```sql
-- The original row, followed by every republish attempt.
SELECT id, attempt, status, published_ts, arrived_ts, rc
FROM mqtt_message_tracker
WHERE id = '3f2a9c...' OR origin_id = '3f2a9c...'
ORDER BY published_ts;
```

How to read the result:

- only the original row: no republish was recorded;
- a second row with `origin_id` set and `status = 'confirmed'`: that republish was accepted by the
  broker;
- a republish row still `failed` or `unconfirmed`: that attempt did not confirm, and another
  republish is still possible.

The republish row's own `published_ts` and `arrived_ts` show when it was published and when the broker
confirmed it, which is later than the original's `published_ts`.

For every message with no confirmed attempt (the tool's default):

```sql
-- Originals with no confirmed attempt, whose own status is failed, unconfirmed, or inflight.
SELECT o.id, o.topic, o.status, o.published_ts
FROM mqtt_message_tracker AS o
WHERE o.status IN ('failed', 'unconfirmed', 'inflight') AND o.origin_id IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM mqtt_message_tracker AS r
      WHERE r.origin_id = o.id AND r.status = 'confirmed')
ORDER BY o.published_ts;
```

A row appears here when it was never republished, or when its republish attempts exist but none
is `confirmed` yet (an attempt that is still `inflight` has not finished).

For every message with its republish attempts and outcome:

```sql
-- Every original, with its republish attempts and outcomes.
SELECT o.id, o.topic, o.status, o.published_ts,
       COUNT(r.id) AS attempts,
       SUM(r.status = 'confirmed') AS confirmed_attempts
FROM mqtt_message_tracker AS o
LEFT JOIN mqtt_message_tracker AS r ON r.origin_id = o.id
WHERE o.origin_id IS NULL
GROUP BY o.id
ORDER BY o.published_ts;
```

How to read the counts:

- `attempts` counts every republish row, whatever its status. `0` means nothing was republished.
- `confirmed_attempts` counts the republish attempts where `status = 'confirmed'`. It is empty
  (`NULL`) when `attempts` is `0`, because there are no rows to sum.
- `confirmed_attempts > 0` means the message was delivered. A value lower than `attempts` means
  some attempts failed but a later one succeeded.

For example, an original with `attempts = 1` and `confirmed_attempts = 1` was republished once
and the broker accepted that republish. An original with `attempts = 0` and an empty
`confirmed_attempts` has not been republished at all. When nothing was confirmed, the latest
attempt's status is the message's current status.

`ORDER BY o.published_ts` lists the oldest first; use `DESC` for the newest first.

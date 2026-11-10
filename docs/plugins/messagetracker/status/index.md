---
title: Status
parent: MQTTMessageTracker
ancestor: MQTTMessageTracker
nav_order: 4
---
{% include messagetracker_warning.html %}

`mqtttracker status` shows the `failed` and `unconfirmed` messages and whether a resend was
accepted by the broker. It reads the tracker database directly, so it does not need MQTTPublish to
be running.

`mqtttracker` is one tool with `resend`, `prune` and `status` subcommands. The config file is a
global `--config` option, so it comes before the subcommand:

```shell
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf status
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf status --unresolved
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

The original `failed` or `unconfirmed` row is never changed, so "eventually sent" means that at
least one row with `origin_id` equal to the original's `id` has status `confirmed`. A `confirmed`
resend means the broker accepted it, not that a subscriber received it.

The default summary lists each message with:

| column | meaning |
| --- | --- |
| `ID` | the row id, the same id in the log line. |
| `TOPIC` | the topic the message was published on. |
| `ORIGINAL STATUS` | the original row's status, `failed` or `unconfirmed`. |
| `ORIGINALLY SENT` | when the original was handed to paho. |
| `ATTEMPTS` | the number of resend rows, whatever their status. |
| `CONFIRMED` | how many of those resends the broker confirmed. |
| `FINAL STATUS` | `sent`, `pending`, or `not resent`. |

The outcomes mean:

- `sent`: at least one resend is `confirmed`;
- `pending`: resends exist, but none is confirmed yet (one may still be `sent`);
- `not resent`: no resend has been recorded.

## Options

### --message ID

Show one original message and its resends, in publish order.

Use the id from the `ERROR` log line. The output shows the original and each resend, including its
`attempt` and `origin_id`. If no row has that id or points at it, the command prints a message and
exits `1`.

### --unresolved

Only show messages with no confirmed resend. This is the outstanding work: never resent, or
resent without a confirmation.

### --topic GLOB

Only show messages whose topic matches the glob, for example `weather/outTemp_*`.

### --limit COUNT

The maximum number of messages to show.
Default is `100`; `0` shows every message.

## The same information in SQL

The status command runs these queries. They are useful when the tool is not installed, or for a
monitor that queries the database directly.

For one message, starting from the id in the log:

```sql
-- The original row, followed by every resend of it.
SELECT id, attempt, status, sent_ts, arrived_ts, rc
FROM mqtt_message_tracker
WHERE id = '3f2a9c...' OR origin_id = '3f2a9c...'
ORDER BY sent_ts;
```

How to read the result:

- only the original row: no resend was recorded;
- a second row with `origin_id` set and `status = 'confirmed'`: that resend was accepted by the
  broker;
- a resend row still `failed` or `unconfirmed`: that attempt did not confirm, and another resend
  is still possible.

The resend row's own `sent_ts` and `arrived_ts` show when it was sent and when the broker
confirmed it, which is later than the original's `sent_ts`.

For every message that is still unresolved:

```sql
-- Failed or unconfirmed originals with no confirmed resend.
SELECT o.id, o.topic, o.status, o.sent_ts
FROM mqtt_message_tracker AS o
WHERE o.status IN ('failed', 'unconfirmed')
  AND NOT EXISTS (
      SELECT 1 FROM mqtt_message_tracker AS r
      WHERE r.origin_id = o.id AND r.status = 'confirmed')
ORDER BY o.sent_ts;
```

A row appears here when it was never resent, or when its resends exist but none is `confirmed`
yet (a resend that is still `sent` has not finished).

For every message with its resend attempts and outcome:

```sql
-- Every failed or unconfirmed original, with its resend attempts and outcomes.
SELECT o.id, o.topic, o.status, o.sent_ts,
       COUNT(r.id) AS attempts,
       SUM(r.status = 'confirmed') AS confirmed_attempts
FROM mqtt_message_tracker AS o
LEFT JOIN mqtt_message_tracker AS r ON r.origin_id = o.id
WHERE o.status IN ('failed', 'unconfirmed')
GROUP BY o.id
ORDER BY o.sent_ts;
```

How to read the counts:

- `attempts` counts every resend row, whatever its status. `0` means nothing was resent.
- `confirmed_attempts` counts the resends where `status = 'confirmed'`. It is empty (`NULL`) when
  `attempts` is `0`, because there are no rows to sum.
- `confirmed_attempts > 0` means the message was eventually sent. A value lower than `attempts`
  means some attempts failed but a later one succeeded.

For example, an original with `attempts = 1` and `confirmed_attempts = 1` was resent once and the
broker accepted that resend. An original with `attempts = 0` and an empty `confirmed_attempts` has
not been resent at all.

`ORDER BY o.sent_ts` lists the oldest first; use `DESC` for the newest first.

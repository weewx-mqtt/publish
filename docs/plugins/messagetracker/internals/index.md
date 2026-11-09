---
title: Internals
parent: MQTTMessageTracker
ancestor: MQTTMessageTracker
nav_order: 5
---
{% include messagetracker_warning.html %}

Implementation notes for `MQTTMessageTracker`.
They are not needed to install or use the plugin.
The options are in [Configuration](../configuration/index.md), and the resend and prune behavior
is in [Resending messages](../resend/index.md) and [Pruning](../prune/index.md).

## What is tracked

Each message published to a tracked topic records a row.

- `id`: a unique id for the row.
- `mid`: the MQTT message id.
- `dateTime`: the WeeWX timestamp of the data.
- `sent_ts`: when the message was handed to paho.
- `arrived_ts`: when paho reported it published, `NULL` for anything that is not `confirmed`.
- `status`: what is known about the message.
- `unconfirmed_ts`: when the tracker stopped waiting for the arrival, `NULL` unless the status is
  `unconfirmed`.
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

## Status lifecycle

`sent` is transient. While the tracker is running, a row is expected to move to `confirmed`, or to
`failed` when paho refuses the publish. If the connection is lost, the rows in flight are marked
`unconfirmed`; otherwise a row whose arrival never arrives is kept until the tracker stops, which
marks it `unconfirmed`. The topic's `error_retention` then bounds it.

A `failed` publish, and a resend that paho refuses, are logged at `ERROR` with the topic, `rc`,
`mid` and the row's `id`. A log monitor can follow the message straight to its row without
searching the table by topic and time.

`unconfirmed` does not mean the message was not delivered. It means the tracker cannot tell: paho
never reported the arrival, and no further report can arrive. That is why it is recorded as its
own status instead of an empty `arrived_ts`.

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

A `confirmed` row is also not proof of delivery to a subscriber. Paho reports it when the broker
acknowledges the publish: a PUBACK for QoS 1, or a PUBCOMP for QoS 2, which completes the
exactly-once handshake. Either way it means the broker accepted the message. QoS is enforced per
leg, publisher to broker and broker to subscriber, so the publisher's handshake says nothing about
whether a subscriber received it; a subscriber with a lower QoS gets weaker delivery guarantees.
With `retain`, it also means the broker stored the message.

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

## Resend rows

A resend is a new row, so the original is never changed:

| id | topic | status | origin_id | attempt |
| --- | --- | --- | --- | --- |
| A | weather/outTemp_F | unconfirmed | NULL | NULL |
| B | weather/outTemp_F | confirmed | A | 1 |

The resend copies the topic, QoS, retain flag, `dateTime` and payload of the original.
Its `origin_id` is the original row and `attempt` counts the resends of that message from 1.
Resending a resend keeps the chain flat under the original, so that message's history is:

```sql
SELECT id, attempt, mid, sent_ts, arrived_ts, status, rc
FROM mqtt_message_tracker WHERE origin_id = ? ORDER BY attempt
```

The write sequence matches the tracker: the resend is inserted as `sent` after paho accepts it,
then updated to `confirmed` or `unconfirmed`.

## Maintenance SQL

`bin/user/mqttprune.py` is the supported way to delete unconfirmed rows.
If the tool is not installed, the same can be done with SQL:

```sql
DELETE FROM mqtt_message_tracker WHERE status = 'unconfirmed' AND sent_ts < ?
```

Deleting an original row while a `confirmed` resend remains leaves that resend's `origin_id`
pointing at a row that no longer exists; the resend row is self-contained, so it still resends
and prunes normally.

## Writer thread and SQLite locking

The tracker writes from its own thread, in batches and short transactions.
The default SQLite `timeout` is 5 seconds.
If the database is busy, the batch is logged as an error and dropped; publishing is not blocked.
With a separate database, this contention is with other writers of that file, not with the weather
archive.

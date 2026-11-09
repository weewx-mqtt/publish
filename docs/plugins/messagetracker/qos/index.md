---
title: QoS in detail
parent: MQTTMessageTracker
ancestor: MQTTMessageTracker
nav_order: 5
---
{% include messagetracker_warning.html %}

## QoS is per leg

A publish crosses two legs:

```text
publisher  --->  broker  --->  subscriber
```

QoS is negotiated and enforced separately on each leg. A publisher using QoS 2 has an exactly-once
handshake with the broker. What the broker then does with the message is a second handshake with
each subscriber, using that subscriber's own QoS.

The subscriber's effective QoS is the lower of the publish QoS and its subscription QoS. A
subscriber that subscribes at QoS 0 gets at-most-once delivery even when the publisher uses QoS 2.

There is no end-to-end acknowledgement in MQTT. The publisher is never told whether the broker
forwarded the message, whether a subscriber received it, or whether there was a subscriber at all.

## Publisher to broker

| QoS | Packets | Paho reports the publish | Guarantee |
| --- | --- | --- | --- |
| 0 | PUBLISH | when the packet is written to the socket | at most once |
| 1 | PUBLISH, PUBACK | on PUBACK | at least once |
| 2 | PUBLISH, PUBREC, PUBREL, PUBCOMP | on PUBCOMP | exactly once |

QoS 2:

```text
publisher                     broker
   PUBLISH  (qos 2)   --->
                      <---    PUBREC
   PUBREL             --->
                      <---    PUBCOMP
```

PUBCOMP is the final packet of the **publisher's** handshake. It means the broker accepted the
message and took ownership of it: it has committed the message and will not accept a duplicate of
that packet id. It does **not** mean the broker has forwarded the message, and it says nothing
about any subscriber.

A QoS 0 publish has no acknowledgement at all. Paho reports it once the bytes are written, so a
`confirmed` row would only mean "written to the socket". That is why the tracker rejects topics
published with QoS 0.

## Broker to subscriber

| Subscriber QoS | Guarantee | Reported back to the publisher |
| --- | --- | --- |
| 0 | at most once | nothing |
| 1 | at least once | nothing |
| 2 | exactly once | nothing |

The broker may deliver before, during, or after it completes the publisher's handshake. The
publisher cannot observe the order, and none of the subscriber's acknowledgements reach it.

Whether an undelivered message survives depends on the subscriber's session and the broker:

- with `clean_session = false`, it can be delivered when the subscriber reconnects;
- with `clean_session = true`, a disconnect drops it;
- some brokers retry while the subscriber is still connected, some only on reconnect.

## Retain

`retain = true` stores the message on the broker as the topic's retained value. This happens when
the broker accepts the publish, independently of any subscriber. A future subscriber receives the
retained value when it subscribes, even if no subscriber received the original publish.

The retained value outlives the tracker row. Pruning a `confirmed` row does not remove it; clear it
with a retained publish that has an empty payload.

## Example: QoS 2, retain, and a subscriber that never acknowledges

A topic publishes with `qos = 2` and `retain = true`. One subscriber is connected but never
acknowledges anything.

1. The publisher sends the PUBLISH with QoS 2 and the retain flag.
2. The broker performs its handshake with the publisher (PUBREC, PUBREL, PUBCOMP).
3. Paho reports the publish on PUBCOMP, and the tracker marks the row `confirmed`.
4. The broker stores the message as the topic's retained value.
5. The broker separately tries to deliver to the subscriber. That leg never completes, because
   the subscriber never answers.

The row stays `confirmed` throughout. It records steps 2–4, all of which are publisher-side or
broker-side facts. Step 5 is invisible to the tracker, and the broker does not wait for it: a
stuck subscriber does not delay or retract the PUBCOMP.

The retained value outlives the row and the subscriber. Any future subscriber to the topic
receives it on subscribe, even if this subscriber never did.

## What this means for the tracker

A `confirmed` row records the broker's acceptance of the publish, not delivery to a subscriber.
The tracker therefore provides at-least-once delivery end to end, and consumers must be idempotent,
for example by deduplicating on `dateTime`.

A resend is a new publish with a new packet id, so even QoS 2 topics can deliver the same
application message more than once. See [QoS and duplicate delivery](../index.md#qos-and-duplicate-delivery)
for what that means when resending.

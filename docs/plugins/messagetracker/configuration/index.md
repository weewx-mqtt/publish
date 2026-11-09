---
title: Configuration
parent: MQTTMessageTracker
ancestor: MQTTMessageTracker
nav_order: 1
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
The install adds a `message_tracker_binding`; see [Enabling it](../index.md#enabling-it).
Required; there is no default, so the tracker never writes to the weather database by accident.

### create_database

Whether to create the database if it does not exist.
Valid values: `true` or `false`
Default is `true`.

### table

The name of the table to create and write to.
Default is `mqtt_message_tracker`.

### retention

The default retention, in seconds, for `confirmed` and `failed` rows in topics that do not set their own.
Set to `0` to keep them forever.
Default is `604800` (7 days).

A `confirmed` row is a record of a publish the broker acknowledged. Pruning it frees space but
loses that history. A `failed` row can still be resent, so pruning it removes a message that could
otherwise have been recovered. `retention` does not apply to `unconfirmed` rows.
See [Pruning](../prune/index.md) for how the retentions work.

### unconfirmed_retention

How long, in seconds, to keep `unconfirmed` rows in topics that do not set their own.
Set to `0` to keep them forever.
Default is `0`.

`unconfirmed` rows are the ones a resend can still recover. Keeping them forever preserves the
whole recovery window, but the table can grow after an outage. A finite value bounds the table at
the cost of losing older messages before they are resent. This option does not apply to `confirmed` or
`failed` rows.

A `sent` row is not pruned; the startup sweep and a disconnect mark it `unconfirmed`, which this
option then bounds. See [Pruning](../prune/index.md) to remove them sooner.

### prune_interval

How often, in seconds, to delete rows older than their retention.
Default is `3600`.

### Advanced options

These control the tracker's writer thread. The defaults are suitable for normal use.
See [Internals](../internals/index.md) for the implementation details.

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

### topics

See [topics](topics/index.md) for the `[[topics]]` section and its per-topic options.

### resend

See [resend](resend/index.md) for the `[[resend]]` section.

---
title: Pruning
parent: MQTTMessageTracker
ancestor: MQTTMessageTracker
nav_order: 3
---
{% include messagetracker_warning.html %}

The tracker deletes old messages so that its database does not grow without bound. A message is
the original publish and every republish of it; the record that decides its status also decides when
it is pruned. Two retention options bound the two kinds of message, and a third decides how often
the tracker checks. You can also delete messages yourself with `mqtttracker prune`.

## Retention options

`confirmed_retention` and `error_retention` group messages by their outcome:

- a message with a confirmed attempt is **delivered**, and is kept for `confirmed_retention`;
- a message whose latest attempt is `failed` or `unconfirmed` is **unresolved**, and is kept for
  `error_retention`.

A message is deleted as one whole chain: the original row and every republish attempt. A `sent`
message is still in flight and neither option prunes it; the startup sweep and a disconnect mark
it `unconfirmed`.

### confirmed_retention

How long, in seconds, to keep a delivered message.
Default is `604800` (7 days).
Set to `0` to keep them forever.

The clock starts when the message was confirmed, so a message that was republished and then
confirmed is kept for the full period from that republish attempt, not from the original failure.

Pruning a delivered message frees space and loses history, but nothing that can be republished.
This is the safe retention to shorten when the table is large.

### error_retention

How long, in seconds, to keep an unresolved message.
Default is `0`, which keeps them forever.
Set it to a finite value to bound the table.

The clock starts at the latest attempt, so a message that keeps failing, or that was just
republished, is kept for the full period from that attempt.

Pruning one of these messages removes a message that could still be recovered, so this is the
retention to keep generous. The default of `0` preserves the whole recovery window, which matters
after an outage when a backlog has built up.

### Per-topic values

Both options can be set per topic:

```ini
[MQTTMessageTracker]
    confirmed_retention = 604800
    error_retention = 0

    [[topics]]
        [[[weather/outTemp_F]]]
            # Keep a day of successful publishes, and every error until it is recovered.
            confirmed_retention = 86400
            error_retention = 0
```

A topic without its own value uses the plugin-level value. A topic that is no longer configured
also uses the plugin-level value, so its rows still age out.

### prune_interval

How often, in seconds, the tracker's writer thread checks for rows to delete.
Default is `3600` (hourly).
Set to `0` to disable automatic pruning; the startup sweep still runs.

This is the schedule, not the age. A prune deletes delivered messages older than
`confirmed_retention`, and unresolved messages older than `error_retention`. No pruning
happens while every retention is `0`.

## How a prune runs

The writer thread checks for old messages after it processes queued events, and when the queue has
been idle for `prune_interval`. So retention is a minimum age: a message is deleted at the first
check after its outcome becomes old enough, which can be up to one interval later. With
`prune_interval = 0`, nothing is deleted automatically until you run the tool.

The startup sweep is separate from pruning. It runs when the tracker starts and marks leftover
`sent` rows as `unconfirmed`; it does not delete anything.

## Pruning with mqtttracker prune

To remove messages sooner than their retention allows, or when `error_retention` is `0`, run
`bin/user/mqtttracker.py prune`. `mqtttracker` is one tool with `republish`, `prune` and `status`
subcommands; the config file is a global `--config` option, so it comes before the subcommand.
By default it selects the delivered history: messages with a confirmed attempt, older than
`confirmed_retention`:

```shell
# Select delivered messages older than confirmed_retention.
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune
```

Add `--delete` to remove them:

```shell
# Delete the selected messages.
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --delete
```

To select unresolved messages, ask for those statuses and give them an age:

```shell
# Select unresolved messages older than 30 days.
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --status failed,unconfirmed --older-than 2592000
```

The tool is in the tracker's user directory: `/etc/weewx/bin/user` on a package install (apt,
rpm, openSUSE) and `~/weewx-data/bin/user` on a pip or git install. Run it with the Python that
WeeWX uses. On a package install it finds WeeWX by itself; for an uninstalled source checkout,
add WeeWX's `src` directory to `PYTHONPATH`.

Without `--delete` it only prints the selection. Each line is one message, shown with the id of
its original row (or of the chain when the original was pruned), the status that decides its
retention, and the time that decision was made.

The plan reports both counts, because a message with republish attempts is several rows:
`11 message(s) selected (13 row(s)):`. `--delete` then reports the rows it removed.

Pruning a message deletes its whole chain: the original and every republish attempt. A message
whose outcome changed between the plan and the delete is left alone. It is safe to run while
WeeWX is running.

Deleting an unresolved message discards the only record that its delivery outcome is unknown.
Deleting a delivered message discards the record that it was delivered, but nothing that could be
republished.

A message whose outcome is still `sent` is in flight: the tracker marks it `unconfirmed` when it
restarts, so the tool does not touch it.
See [Internals](../internals/index.md#maintenance-sql) for the equivalent SQL.

## prune options

The first argument is the WeeWX config file. The rest are options.

### --delete

Delete the selection. Without it the tool is a dry run: it prints what it would delete and removes
nothing.

Run it once without `--delete` to see the selection before deleting anything.

### --status STATUS

A comma-separated list of statuses to prune.
Default is `confirmed`.

A message is delivered when any attempt is `confirmed`, so `--status failed` does not select a
message that a republish later delivered. Use `--status failed,unconfirmed` to prune unresolved
messages. `sent` is refused because it may still be in flight (restart WeeWX to mark it
`unconfirmed`).

```shell
# Prune unresolved messages older than 30 days.
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --status failed,unconfirmed --older-than 2592000 --delete
```

### --older-than SECONDS

Select messages whose outcome is older than `SECONDS`.
Default is the retention for the message's status: `confirmed_retention` for a delivered message,
`error_retention` for an unresolved one. With the default `error_retention` of `0`, unresolved
messages are selected only when this option, or a finite `error_retention`, gives them an age.

`--older-than 0` selects every matching message, whatever its age. That is how you clear a backlog
regardless of the configured retention.

```shell
# Every unresolved message, of any age.
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --status failed,unconfirmed --older-than 0 --delete
```

### --topic GLOB

Only prune topics that match the glob.

```shell
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --topic 'weather/outTemp_*' --older-than 2592000 --delete
```

### --limit COUNT

The maximum number of messages to select, oldest first.
Default is `100`; `0` removes the limit.
Each selected message also deletes its whole chain, so the number of rows removed can be higher.
When the limit truncates the selection, the tool reports how many of the matching messages it
selected; use `--limit 0` to select them all.

### --plugin-section NAME

The tracker's config section.
Default is `MQTTMessageTracker`.

### --data-binding NAME

Override the tracker's `data_binding` option.

### --table NAME

Override the tracker's `table` option.

### --version

Print the tool's version and exit.

## Scheduling

`confirmed_retention` and `error_retention` prune messages automatically at the `prune_interval`
cadence. Use the tool on a timer when you want a different age or cadence, or want to prune only
some statuses.

A system cron entry in `/etc/cron.d/mqtttracker-prune`:

```cron
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Every day at 03:15, delete delivered messages older than confirmed_retention.
15 3 * * * weewx /usr/bin/python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --delete >> /var/log/weewx/mqtttracker-prune.log 2>&1
```

The same line in the WeeWX user's crontab (`crontab -u weewx -e`) drops the `weewx` user field.

To clear a backlog of unresolved messages after an outage, ask for those statuses explicitly:

```cron
15 3 * * * weewx /usr/bin/python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --status failed,unconfirmed --older-than 2592000 --limit 1000 --delete >> /var/log/weewx/mqtttracker-prune.log 2>&1
```

- Run as the WeeWX user, not root, so the database permissions match.
- Use the Python that WeeWX uses.
- `--delete` is required; without it the tool is a dry run.
- `--status` defaults to `confirmed`, so a run without it never deletes an unresolved message.
- `--limit` defaults to `100`, so a large backlog clears over several runs. `--limit 0` removes
  the limit.
- The tool is safe while WeeWX is running.
- The exit code is `0` on success and `2` on a config or database error. Cron only sends mail
  when the command writes output, so keep the log and rotate it, or leave stderr unredirected
  with `MAILTO` set. The log directory must exist and be writable by the WeeWX user; `logger -t
  mqtttracker-prune` can be used instead of a file.

A systemd timer is an alternative to cron. For example,
`/etc/systemd/system/mqtttracker-prune.service`:

```ini
[Unit]
Description=Prune the MQTT message tracker

[Service]
Type=oneshot
User=weewx
ExecStart=/usr/bin/python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --delete
```

and `/etc/systemd/system/mqtttracker-prune.timer`:

```ini
[Unit]
Description=Run the MQTT message tracker prune daily

[Timer]
OnCalendar=*-*-* 03:15:00
Persistent=true

[Install]
WantedBy=timers.target
```

Then enable it with `systemctl daemon-reload` and `systemctl enable --now mqtttracker-prune.timer`.
The service's output goes to the journal.

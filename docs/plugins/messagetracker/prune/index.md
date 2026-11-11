---
title: Pruning
parent: MQTTMessageTracker
ancestor: MQTTMessageTracker
nav_order: 3
---
{% include messagetracker_warning.html %}

The tracker deletes old rows so that its database does not grow without bound. Two retention
options decide how long a row is kept, and a third decides how often the tracker checks. You can
also delete rows yourself with `mqtttracker prune`.

## Retention options

`confirmed_retention` and `error_retention` group the statuses by what the row means:

- `confirmed` is success history — a publish the broker accepted.
- `failed` and `unconfirmed` are the recoverable rows a resend can still use.

`sent` is transient and neither option prunes it; the startup sweep and a disconnect mark it
`unconfirmed`.

### confirmed_retention

How long, in seconds, to keep `confirmed` rows.
Default is `604800` (7 days).
Set to `0` to keep them forever.

Pruning a confirmed row frees space and loses history, but nothing that can be resent. This is the
safe retention to shorten when the table is large.

### error_retention

How long, in seconds, to keep `failed` and `unconfirmed` rows.
Default is `0`, which keeps them forever.
Set it to a finite value to bound the table.

Pruning one of these rows removes a message that could still be recovered, so this is the retention
to keep generous. The default of `0` preserves the whole recovery window, which matters after an
outage when a backlog has built up.

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

This is the schedule, not the age. A prune deletes `confirmed` rows older than
`confirmed_retention`, and `failed` or `unconfirmed` rows older than `error_retention`. No pruning
happens while every retention is `0`.

## How a prune runs

The writer thread checks for old rows after it processes queued events, and when the queue has been
idle for `prune_interval`. So retention is a minimum age: a row is deleted at the first check after
it becomes old enough, which can be up to one interval later. With `prune_interval = 0`, nothing is
deleted automatically until you run the tool.

The startup sweep is separate from pruning. It runs when the tracker starts and marks leftover
`sent` rows as `unconfirmed`; it does not delete anything.

## Pruning with mqtttracker prune

To remove rows sooner than their retention allows, or when `error_retention` is `0`, run
`bin/user/mqtttracker.py prune`. `mqtttracker` is one tool with `resend`, `prune` and `status`
subcommands; the config file is a global `--config` option, so it comes before the subcommand:

```shell
# Select failed and unconfirmed rows older than 30 days.
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --older-than 2592000
# Add --delete to remove them.
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --older-than 2592000 --delete
```

The tool is in the tracker's user directory: `/etc/weewx/bin/user` on a package install (apt,
rpm, openSUSE) and `~/weewx-data/bin/user` on a pip or git install. Run it with the Python that
WeeWX uses. On a package install it finds WeeWX by itself; for an uninstalled source checkout,
add WeeWX's `src` directory to `PYTHONPATH`.

Without `--delete` it only prints the selection.

By default a row is selected when it is older than the retention for its status:
`error_retention` for `failed` and `unconfirmed` rows, and `confirmed_retention` for `confirmed`
rows. Because `error_retention` defaults to `0`, a run without `--older-than` selects no error
rows; the confirmed rows still age out at their configured retention.

Pruning a row also deletes the rest of its message chain, so a resent message leaves nothing
behind. A row that changed between the plan and the delete is left alone. It is safe to run while
WeeWX is running.

Deleting an `unconfirmed` row discards the only record that its delivery outcome is unknown.
Deleting a `confirmed` resend discards the record that the message was eventually delivered.

A `sent` row is marked `unconfirmed` when the tracker restarts, so the tool does not touch it, or
any other row in the chain that is still `sent`.
See [Internals](../internals/index.md#maintenance-sql) for the equivalent SQL.

## prune options

The first argument is the WeeWX config file. The rest are options.

### --delete

Delete the selection. Without it the tool is a dry run: it prints what it would delete and removes
nothing.

Run it once without `--delete` to see the selection before deleting anything.

### --status STATUS

A comma-separated list of statuses to prune.
Default is `failed,unconfirmed`.

Use `--status unconfirmed` to prune only the ambiguous rows, or `--status failed` to prune only
failed publishes. `sent` is refused because it may still be in flight (restart WeeWX to mark it
`unconfirmed`). `confirmed` is not selected by default; `--status confirmed` prunes confirmed rows
older than `confirmed_retention`, which is how you clean up the history between the automatic
prunes or when `prune_interval` is `0`.

```shell
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --status confirmed --delete
```

### --older-than SECONDS

Select rows older than `SECONDS`.
Default is the retention for the row's status: `error_retention` for `failed` and `unconfirmed`
rows, `confirmed_retention` for `confirmed` rows. With the default `error_retention` of `0`, a run
without this option selects no error rows.

`--older-than 0` selects every matching row, whatever its age. That is how you clear a backlog
regardless of the configured retention.

```shell
# Every failed and unconfirmed row, of any age.
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --older-than 0 --delete
```

### --topic GLOB

Only prune topics that match the glob.

```shell
python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --topic 'weather/outTemp_*' --older-than 2592000 --delete
```

### --limit COUNT

The maximum number of rows to select, oldest first.
Default is `100`; `0` removes the limit.
Each selected row also deletes the rest of its message chain, so the number of rows removed can be
higher. When the limit truncates the selection, the tool reports how many of the matching messages
it selected; use `--limit 0` to select them all.

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

`confirmed_retention` and `error_retention` prune rows automatically at the `prune_interval`
cadence. Use the tool on a timer when you want a different age or cadence, or want to prune only
some statuses.

A system cron entry in `/etc/cron.d/mqtttracker-prune`:

```cron
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Every day at 03:15, delete failed and unconfirmed rows older than 30 days.
15 3 * * * weewx /usr/bin/python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --older-than 2592000 --delete >> /var/log/weewx/mqtttracker-prune.log 2>&1
```

The same line in the WeeWX user's crontab (`crontab -u weewx -e`) drops the `weewx` user field.

To clear a backlog after an outage, widen the age, include `failed`, and raise the limit:

```cron
15 3 * * * weewx /usr/bin/python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --status unconfirmed,failed --older-than 2592000 --limit 1000 --delete >> /var/log/weewx/mqtttracker-prune.log 2>&1
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
  mqtttracker-prune` can be used instead of a file.

A systemd timer is an alternative to cron. For example,
`/etc/systemd/system/mqtttracker-prune.service`:

```ini
[Unit]
Description=Prune the MQTT message tracker

[Service]
Type=oneshot
User=weewx
ExecStart=/usr/bin/python3 /etc/weewx/bin/user/mqtttracker.py --config /etc/weewx/weewx.conf prune --older-than 2592000 --delete
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

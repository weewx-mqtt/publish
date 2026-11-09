---
title: Pruning
parent: MQTTMessageTracker
ancestor: MQTTMessageTracker
nav_order: 3
---
{% include messagetracker_warning.html %}

The tracker deletes old rows so that its database does not grow without bound. Two options decide
how long a row is kept, one for confirmed rows and one for the rows a resend can still use. See
[Configuration](../configuration/index.md#confirmed_retention) for them and their defaults.

## How retention works

`confirmed_retention` bounds `confirmed` rows — the success history. `error_retention` bounds
`failed` and `unconfirmed` rows, the messages a resend can still recover. Each uses the topic's
value, or the plugin-level value for topics that are no longer configured. `0` keeps a group
forever. `sent` rows are not pruned; the startup sweep and a disconnect mark them `unconfirmed`.

Shortening `confirmed_retention` only loses history. Shortening `error_retention` also makes older
messages unrecoverable, so it is the one to keep generous.

## Pruning with mqttprune.py

To remove rows sooner than their retention allows, run `bin/user/mqttprune.py`:

```shell
# Select unconfirmed rows older than 30 days.
python /usr/share/weewx/bin/user/mqttprune.py /etc/weewx/weewx.conf --older-than 2592000
# Add --delete to remove them.
python /usr/share/weewx/bin/user/mqttprune.py /etc/weewx/weewx.conf --older-than 2592000 --delete
```

Without `--delete` it only prints the selection.

By default a row is selected when it is older than its topic's `error_retention`. Because that
defaults to `0`, a run without `--older-than` selects nothing. `--older-than 0` selects every
matching row, including topics whose retention is `0`.

- `--status unconfirmed` is the default. Use `--status failed`, or `failed,unconfirmed`, to
  include `failed`. `sent` is refused (it may be in flight; restart WeeWX to mark it
  `unconfirmed`) and `confirmed` is refused (the automatic prune handles it).
- `--topic` filters with a glob, and `--limit` caps the run (default `100`, oldest first).
- `--plugin-section`, `--data-binding` and `--table` select a tracker configured elsewhere.

The tool deletes by id and status, so a row that changed between the plan and the delete is left
alone. It is safe to run while WeeWX is running.

Deleting an `unconfirmed` row discards the only record that its delivery outcome is unknown.
Deleting an original row while a `confirmed` resend remains leaves that resend's `origin_id`
pointing at a row that no longer exists; the resend row is self-contained, so it still resends
and prunes normally.

A `sent` row is marked `unconfirmed` when the tracker restarts, so the tool does not touch it.
See [Internals](../internals/index.md#maintenance-sql) for the equivalent SQL.

## Scheduling

`confirmed_retention` and `error_retention` prune rows automatically. `prune_interval` sets how
often the tracker checks (default hourly); `0` disables the check, leaving `mqttprune` as the only
way to delete rows. Use the tool on a timer when you want a shorter age or a different cadence, or
want to prune only some statuses.

Run it once without `--delete` first, to see the selection.

A system cron entry in `/etc/cron.d/mqttprune`:

```cron
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Every day at 03:15, delete unconfirmed rows older than 30 days.
15 3 * * * weewx /usr/bin/python3 /usr/share/weewx/bin/user/mqttprune.py /etc/weewx/weewx.conf --older-than 2592000 --delete >> /var/log/weewx/mqttprune.log 2>&1
```

The same line in the WeeWX user's crontab (`crontab -u weewx -e`) drops the `weewx` user field.

To clear a backlog after an outage, widen the age, include `failed`, and raise the limit:

```cron
15 3 * * * weewx /usr/bin/python3 /usr/share/weewx/bin/user/mqttprune.py /etc/weewx/weewx.conf --status unconfirmed,failed --older-than 2592000 --limit 1000 --delete >> /var/log/weewx/mqttprune.log 2>&1
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
  mqttprune` can be used instead of a file.

A systemd timer is an alternative to cron. For example,
`/etc/systemd/system/mqttprune.service`:

```ini
[Unit]
Description=Prune the MQTT message tracker

[Service]
Type=oneshot
User=weewx
ExecStart=/usr/bin/python3 /usr/share/weewx/bin/user/mqttprune.py /etc/weewx/weewx.conf --older-than 2592000 --delete
```

and `/etc/systemd/system/mqttprune.timer`:

```ini
[Unit]
Description=Run the MQTT message tracker prune daily

[Timer]
OnCalendar=*-*-* 03:15:00
Persistent=true

[Install]
WantedBy=timers.target
```

Then enable it with `systemctl daemon-reload` and `systemctl enable --now mqttprune.timer`.
The service's output goes to the journal.

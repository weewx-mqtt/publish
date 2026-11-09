---
title: Pruning
parent: MQTTMessageTracker
ancestor: MQTTMessageTracker
nav_order: 3
---
{% include messagetracker_warning.html %}

The tracker deletes old rows so that its database does not grow without bound. The retention
options decide how long each kind of row is kept. See
[Configuration](../configuration/index.md#retention) for the options and their defaults.

## How retention works

The retentions decide how long a message remains available to resend. `retention` bounds `confirmed`
and `failed` rows; `unconfirmed_retention` bounds the uncertain rows a resend can still use.
Shortening either makes older messages unrecoverable; keeping them at `0` preserves recovery but
lets the table grow.

The tracker prunes `confirmed` and `failed` rows by age, using each topic's `retention` (or the
plugin-level `retention` for topics that are no longer configured). `unconfirmed` rows are pruned
by `unconfirmed_retention`, which defaults to `0` (never). `sent` rows are not pruned; the startup
sweep and a disconnect mark them `unconfirmed`.

## Pruning with mqttprune.py

To remove unconfirmed rows sooner, or when `unconfirmed_retention` is `0`, run
`bin/user/mqttprune.py`:

```shell
python /usr/share/weewx/bin/user/mqttprune.py /etc/weewx/weewx.conf
python /usr/share/weewx/bin/user/mqttprune.py /etc/weewx/weewx.conf --delete
```

Without `--delete` it only prints the selection.

By default a row is selected when it is older than its topic's `retention` — the age the normal
policy uses. Use `--older-than` to match `unconfirmed_retention`, or to prune sooner.
`--older-than 0` selects every matching row, including topics whose retention is `0`.

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

`unconfirmed_retention` bounds unconfirmed rows automatically. Use the tool on a timer when you
want a different age or cadence, want to prune `failed` early, or leave `unconfirmed_retention`
at `0`.

Run it once without `--delete` first, to see the selection.

A system cron entry in `/etc/cron.d/mqttprune`:

```cron
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Every day at 03:15, delete unconfirmed rows older than their topic's retention.
15 3 * * * weewx /usr/bin/python3 /usr/share/weewx/bin/user/mqttprune.py /etc/weewx/weewx.conf --delete >> /var/log/weewx/mqttprune.log 2>&1
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
ExecStart=/usr/bin/python3 /usr/share/weewx/bin/user/mqttprune.py /etc/weewx/weewx.conf --delete
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

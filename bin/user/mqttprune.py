#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
""" Delete the message tracker rows that the retention policy keeps.

    The tracker prunes 'acked' and 'failed' rows by age, but keeps 'sent' and
    'unconfirmed' rows, because they may still be delivered or can still be
    replayed. This tool removes the ones an operator no longer wants, with the
    configured retention as the default age.

    The tool is a dry run unless --delete is given.
"""

# pylint: disable=wrong-import-order
import argparse
import fnmatch
import os
import sys
import time

# When run as a script, the 'user' package is not on the path.
_bin_root = os.getenv('BIN_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _bin_root not in sys.path:
    sys.path.append(_bin_root)

import weedb  # pylint: disable=wrong-import-position
from weeutil.weeutil import to_int  # pylint: disable=wrong-import-position

import user.mqttpublish  # pylint: disable=wrong-import-position
import user.mqttmessagetracker  # pylint: disable=wrong-import-position

VERSION = user.mqttpublish.VERSION

# A 'sent' row may be in flight and an 'acked' row is pruned by the tracker.
PRUNE_STATUSES = (user.mqttmessagetracker.STATUS_UNCONFIRMED,
                  user.mqttmessagetracker.STATUS_FAILED)

DEFAULT_STATUS = user.mqttmessagetracker.STATUS_UNCONFIRMED
DEFAULT_LIMIT = 100

# The number of rows deleted in one transaction.
_BATCH_SIZE = 100


class PruneError(Exception):
    """ A prune failure. """


def _retention_for(row, topic_retention, default_retention, older_than):
    """ The age a row must exceed to be pruned. """
    if older_than is not None:
        return older_than
    return topic_retention.get(row['topic'], default_retention)


def _is_old_enough(row, retention, now):
    """ Whether the row is older than its retention. A retention of 0 keeps it forever. """
    if retention <= 0:
        return False
    return row['sent_ts'] < now - retention


def _wanted(row, statuses, topic, retention, now):
    """ Whether the row passes the filters. """
    if row['status'] not in statuses:
        return False
    if topic and not fnmatch.fnmatchcase(row['topic'], topic):
        return False
    return _is_old_enough(row, retention, now)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def select_rows(rows, statuses=None, topic_retention=None, default_retention=None,
                older_than=None, topic=None, limit=DEFAULT_LIMIT, now=None):
    """ Select the rows to delete, oldest first.

        By default a row is selected when it is older than its topic's retention.
        An explicit 'older_than' overrides the configured retention. """
    statuses = tuple(statuses or (DEFAULT_STATUS,))
    topic_retention = topic_retention or {}
    if default_retention is None:
        default_retention = user.mqttmessagetracker.DEFAULT_RETENTION
    now = time.time() if now is None else now

    selected = [row for row in rows
                if _wanted(row, statuses, topic,
                           _retention_for(row, topic_retention, default_retention, older_than), now)]
    selected.sort(key=lambda row: (row['sent_ts'], row['id']))
    if limit is not None and limit > 0:
        selected = selected[:limit]
    return selected


def delete_rows(connection, table, rows):
    """ Delete the selected rows, in short batches.

        The status is part of the delete, so a row that changed after it was
        selected is left alone. """
    deleted = 0
    for start in range(0, len(rows), _BATCH_SIZE):
        chunk = rows[start:start + _BATCH_SIZE]
        with weedb.Transaction(connection) as cursor:
            for row in chunk:
                cursor.execute(f"DELETE FROM {table} WHERE id = ? AND status = ?",
                               (row['id'], row['status']))
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE id = ?", (row['id'],))
                if cursor.fetchone()[0] == 0:
                    deleted += 1
    return deleted


def _resolve(config_dict, options):
    """ Resolve the tracker options and the retention to prune by. """
    try:
        plugin_dict, database_dict, table = user.mqttmessagetracker.tool_config(
            config_dict, options.plugin_section, options.data_binding, options.table)
    except user.mqttmessagetracker.TrackerConfigError as exception:
        raise PruneError(str(exception)) from exception

    default_retention = user.mqttmessagetracker.DEFAULT_RETENTION
    retention = to_int(plugin_dict.get('retention', default_retention))
    if retention is None:
        retention = default_retention

    topic_dicts = plugin_dict.get('topics')
    topic_retention = {}
    if topic_dicts:
        topic_retention = user.mqttmessagetracker.topic_retentions(topic_dicts, retention)
    return database_dict, table, topic_retention, retention


def prune(config_dict, options, out=None):
    """ Select the rows and, when asked to, delete them. """
    out = sys.stdout if out is None else out
    database_dict, table, topic_retention, retention = _resolve(config_dict, options)

    try:
        connection = weedb.connect(database_dict)
    except weedb.DatabaseError as exception:
        raise PruneError(f"Unable to open the message tracker database: {exception}") from exception

    try:
        rows = user.mqttmessagetracker.fetch_rows(connection, table)
        selected = select_rows(rows, statuses=options.status, topic_retention=topic_retention,
                               default_retention=retention, older_than=options.older_than,
                               topic=options.topic, limit=options.limit)
        user.mqttmessagetracker.print_plan(selected, out)
        if not options.delete or not selected:
            return selected
        deleted = delete_rows(connection, table, selected)
    except weedb.DatabaseError as exception:
        raise PruneError(f"Unable to use the message tracker table {table}: {exception}") from exception
    finally:
        connection.close()

    print(f"Deleted {deleted} row(s).", file=out)
    return selected


def _statuses(value):
    """ Parse the statuses a row can be pruned from. """
    statuses = [status.strip() for status in value.split(',') if status.strip()]
    invalid = [status for status in statuses if status not in PRUNE_STATUSES]
    if invalid:
        raise argparse.ArgumentTypeError(
            f"invalid status(es) {', '.join(invalid)}, choose from {', '.join(PRUNE_STATUSES)}")
    return statuses


def build_parser():
    """ The command line options. """
    parser = argparse.ArgumentParser(
        description="Delete the message tracker rows that the retention policy keeps.",
        epilog="Without --delete the selection is only printed, nothing is removed.")
    parser.add_argument('config_file', help="The WeeWX config file, for example /etc/weewx/weewx.conf.")
    parser.add_argument('--version', action='version', version=f'%(prog)s {VERSION}')

    parser.add_argument('--plugin-section', default=user.mqttmessagetracker.DEFAULT_PLUGIN_SECTION,
                        help=(f"The config section of the tracker plugin. "
                              f"Default is {user.mqttmessagetracker.DEFAULT_PLUGIN_SECTION}."))
    parser.add_argument('--data-binding', default=None,
                        help="Override the tracker's data_binding option.")
    parser.add_argument('--table', default=None,
                        help="Override the tracker's table option.")

    parser.add_argument('--status', type=_statuses, default=[DEFAULT_STATUS], metavar='STATUS',
                        help=(f"The statuses to prune, comma separated. "
                              f"Default is {DEFAULT_STATUS}. Choose from "
                              f"{', '.join(PRUNE_STATUSES)}."))
    parser.add_argument('--older-than', type=int, default=None, metavar='SECONDS',
                        help="Only prune rows older than SECONDS. Default is the topic's retention.")
    parser.add_argument('--topic', default=None, metavar='GLOB',
                        help="Only prune topics that match the glob, for example 'weather/outTemp_*'.")
    parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT, metavar='COUNT',
                        help=f"The maximum number of rows to prune. Default is {DEFAULT_LIMIT}.")
    parser.add_argument('--delete', action='store_true',
                        help="Delete the selected rows. Without it nothing is removed.")
    return parser


def run(options, out=None, err=None):
    """ Run the tool, returning the exit code. """
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    try:
        config_dict = user.mqttmessagetracker.read_config(options.config_file)
        prune(config_dict, options, out)
    except (user.mqttmessagetracker.TrackerConfigError, PruneError) as exception:
        print(f"mqttprune: {exception}", file=err)
        return 2
    return 0


def main(argv=None):
    """ The command line entry point. """
    return run(build_parser().parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())

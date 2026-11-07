# AGENTS.md

WeeWX extension **MQTTPublish** (`weewx-mqtt/publish`): a WeeWX service that publishes
loop/archive data to MQTT, plus a plugin framework for extra processing (Home Assistant
discovery, aggregate values, archive values). Requires WeeWX 5.x and paho-mqtt 1.6.1+.

## Role & boundaries

- `bin/user/mqttcommon.py` is the paho mqtt code shared with the other weewx-mqtt extensions,
  vendored **verbatim**: never edit this copy. Publish uses `Logger`/`LoggerThread`; the throttle
  is unwired.
- Change it in the [mqttcommon](https://github.com/weewx-mqtt/mqttcommon) repository and sync
  into every consumer with `commonrepos.sh`; that repository's `AGENTS.md` has the procedure and
  the `MQTTCOMMON_API` bump ritual.
- `bin/user/mqtthaconfig.py` is a deprecated shim re-exporting `mqttconfigha.py`. Do not add code.

## Layout

- `bin/user/mqttpublish.py` — the whole service: `MQTTPublish(StdService)`, `PluginManager`,
  the publishers, the queue/process plumbing, and a standalone CLI.
- `bin/user/mqtt{aggregatevalues,archivevalues,configha}.py` — plugins, referenced from
  weewx.conf by dotted path (`plugin = user.mqttconfigha.MQTTConfigHA`) and instantiated
  via `weeutil.weeutil.get_object`.
- `bin/user/mqttmessagetracker.py` — plugin that records published messages in a separate
  WeeWX database. Uses the `mqtt_publish` (delay) and `on_mqtt_publish` callbacks, and the
  optional plugin `shutdown` to flush its writer thread.
- `bin/user/mqttresend.py` — CLI that republishes the tracker's `failed`/`unconfirmed` rows;
  `bin/user/mqttprune.py` — CLI that applies the tracker's retention policy. Neither is loaded
  by WeeWX; both are run directly (see `docs/plugins/messagetracker/`).
- `install.py` — WeeWX `ExtensionInstaller`; the `MQTTPUBLISH_CONFIG` string is the template
  inserted into `weewx.conf`.
- `docs/` — Jekyll site (GitHub Pages, baseurl `/publish`); the user-facing option reference.
  READMEs are docs-first: the project README lives under `docs/`, not at the repo root.
- `bin/user/tests/unit/` — stubbed-paho unit tests. `bin/user/tests/integ/` — broker-backed
  smoke tests (`test_reconnect.py`, `test_resend.py`) that spawn their own mosquitto on a free
  port and are skipped when it is not installed. There are no func/e2e dirs; CI disables those
  suites.

## Environment

Tests need WeeWX importable. CI pip-installs it; locally `.devenv`/`.env` point at a sibling
weewx checkout (`../weewx`). Run everything from the repo root:

```bash
source .devenv
export PYTHONPATH="$WEEWX_PYTHONPATH"   # == bin, or bin:../weewx/src
```

Without `PYTHONPATH=bin` you get `ModuleNotFoundError: No module named 'user'`.
If `../weewx` is absent, `pip install weewx` and use `PYTHONPATH=bin` instead.

Optional shortcuts (require `.devenv` sourced): scripts in
`~/weewx_dev/weewx-extensions/development-tools/tools/` — `verify.sh` is the full
pre-commit gate (environment, lint including the test tree, actionlint, shared config and
common-repo checks, all test suites). Also `unittests.sh`, `lint.sh`, `coverage.sh`,
`alltests.sh`.

## Commands

```bash
# Before committing: the same gate the CI runs.
source .devenv
~/weewx_dev/weewx-extensions/development-tools/tools/verify.sh

# All unit tests (currently 507, ~6s, no broker or network needed — paho is mocked/stubbed)
pytest bin/user/tests/unit

# One file / one test (nodeid form)
pytest bin/user/tests/unit/test_mqtthaconfig.py
pytest bin/user/tests/unit/test_mqtthaconfig.py::test_MQTTHomeAssistantConfig::test_init

# Or invoke a test file directly (note: class name, then method name)
python bin/user/tests/unit/test_mqtthaconfig.py test_MQTTHomeAssistantConfig test_init

# Integration smoke tests: real broker + real paho. test_reconnect kills and restarts the
# broker to verify the loop_start reconnect; test_resend republishes tracker rows. Both spawn
# their own mosquitto on a free port (the system broker on 1883 is untouched) and are skipped
# when mosquitto is not installed.
pytest bin/user/tests/integ

# Lint (config: .pylintrc). CI lints the modules via the workflows' `lint-paths` input
# AND the tests with .pylintrc-tests, and fails the build on findings. `verify.sh` runs both.
pylint ./bin/user/mqttpublish.py ./bin/user/mqttarchivevalues.py ./bin/user/mqttconfigha.py \
    ./bin/user/mqttaggregatevalues.py ./bin/user/mqtthaconfig.py ./bin/user/mqttcommon.py \
    ./bin/user/mqttmessagetracker.py ./bin/user/mqttresend.py ./bin/user/mqttprune.py -r n
pylint ./bin/user/tests -r n --rcfile .pylintrc-tests

# Coverage
coverage run --branch -m pytest bin/user/tests/unit
coverage html --include 'bin/user/*.py' --omit bin/user/__init__.py
```

There is no typechecker. `.flake8` (max-line-length 145) is run by CI on the same `lint-paths`
target and fails the build on findings.

## Architecture / behavior

- **paho-mqtt v1 and v2 must both work** (CI tests latest and `paho-mqtt==1.6.1`).
  `Publisher.__init__` derives `self.api` with `mqttcommon.select_api(protocol)`; tests force a
  specific variant with the `api` argument. V2 tests are
  guarded with `@unittest.skipIf(not hasattr(paho.mqtt.client, 'CallbackAPIVersion'), ...)`.
- **Reconnects are paho-native.** `Publisher._connect()` configures
  `mqttcommon.configure_reconnect_delay` and starts `client.loop_start()`; paho's network loop
  thread then owns the connection, and reconnects until the broker is available. Never call
  `client.loop()` manually (it is forbidden while `loop_start()` is running). `max_retries`,
  `wait_between_retries`, and `wait_for_connection` are deprecated and no longer used. A startup
  connect failure still marks the publisher thread for shutdown via `publisher.process = False`
  so the service's thread-restart budget takes over. The integ smoke test
  (`bin/user/tests/integ/test_reconnect.py`) covers this against a real broker.
- **`multiprocess = true` plumbing is fragile.** `QueueProcessor` is a `multiprocessing.Process`
  fed by `PublishWeeWXProcess`, which is deliberately a *thread* that re-queues into a
  `JoinableQueue` (see the comment at `QueueProcessor`) to avoid random queue locks on
  Ubuntu 22.04 / Python 3.10.13. Don't "simplify" it back into a process.
- **The worker is forked, so it inherits locked logging streams.** `multiprocessing` uses
  `fork()`: the child copies the parent's memory, and a lock is just memory, so a lock held at
  the fork instant stays held in the child — by a thread that does not exist there, so nothing
  ever releases it. `logging` re-initialises the *handler* locks in the child, but not the
  internal lock of the handler's **file stream**. If the parent's `LoggerThread` was inside
  `stream.write()`/`flush()` at that moment, the child inherits the stream locked forever.
  The worker's own records go through the logger queue, so it runs normally until code inside
  the child logs *directly* — `weewx.wxxtypes.calc_beaufort` logs its deprecation warning once —
  and that call blocks in `RotatingFileHandler.shouldRollover` -> `stream.seek(0, 2)`. The worker
  then stops draining its queue, and the shutdown item is never seen. That is why the fault
  looked random (it depended on whether the parent happened to be logging at fork time) and
  shutdown-related (the worker was already stuck; Ctrl-C just exposed it). `_start_processor()`
  holds every handler lock across `processor.start()` so no thread can be inside `emit()` during
  the fork, and `TestPublishWeeWXProcess` asserts the acquire/start/release order. Reproduced
  standalone: 60/60 forked children hung on their first log call without the locks, 0/60 with
  them. Don't drop the locking, and don't fork outside `_start_processor()`. (`spawn` would
  avoid inherited state entirely, but the WeeWX config objects handed to the worker are not
  picklable.)
- **Logging is queued, subscribe-style.** `Logger.trace/debug/info/error(msg_id, msg_text)` queue
  entries built by the single entry builder `Logger.create_entry(name, log_type, msg_id, msg_text, archive_timestamp=None)`
  -> `{'name', 'log_type', 'msg_id', 'msg_text', 'thread_id', 'archive_timestamp'}` (native id of the
  emitting thread; `archive_timestamp` is the archive record context the producer supplies —
  the same None here).
  Every application message passes `None` for the message id — publish has no message ids; only
  the shared thread entries (start 122002, exit 122003, invalid 124003) carry one. Beware
  when porting subscribe's throttling: `None` is also subscribe's throttle-*exemption* value, so
  its `msg_id is None` gate would exempt nearly every publish message; the gate must be redesigned
  (key on `msg_text`) instead of ported as-is.
  All producers (mqttpublish and the plugins) must use `create_entry`; never put raw dicts.
  Entries with `log_type: None` are skipped by `log_entry` (monitor flags off, unmapped paho
  levels). `_log_trace/_log_debug/_log_info/_log_error` are the direct sinks (what the
  `LoggerThread` dispatches to; TRACE emits at DEBUG). `Logger` and `LoggerThread` are
  `mqttcommon.Logger`/`mqttcommon.LoggerThread` — publish has no local `Logger` name; the message
  format is the shared `"(%s) %s"` (the separate `ERROR_LOG_FORMAT` is gone), and construction
  passes `log_name=__name__` to the base ctor (the shared prefix — name, thread id,
  and the archive record when there is one — applies) — lines render
  `(MQTTPublish-<class name>-<thread id>) msg` (the base `_format_args` builds that prefix; the name is the bare class name and the thread id is stamped by `create_entry` at enqueue time). The skeleton tests — including the converged default-format rendering — live in the shared `test_mqttcommon.py`; publish has no local logging tests.
  `MQTTPublish.__init__` creates the queue
  (`multiprocessing.Queue` in multiprocess mode, via `_create_logger_queue`) and passes it to
  `mqttcommon.Logger(<component name>, log_queue=..., log_name=__name__)`, which owns the daemon `LoggerThread` that drains it. Flush with
  `Logger.shutdown(timeout)` — `_shut_down_logger` passes the
  configured `wait_for_thread_shutdown`; when the thread is stuck, the warning is built and
  logged directly, not queued. Tests that assert on log output must drain first (shutdown), or
  call `log_entry` directly after a shutdown.
  Shutdown failures use `mqttpublish.log_direct(name, log_type, msg_text)`, which renders the
  same `(name-thread id) msg` line from the calling thread: once the logger thread is stuck,
  anything still queued is never written. `log_direct` is for the service's own process only
  (the service and the feeder thread); the worker and its plugins can be a fork of it and must
  keep to the queue.

## Plugin contract

A plugin class exposes `get_callbacks()` returning a list of
`{callback_name: {'timing': 'immediate'|'delay', 'callback': fn}}` for
`on_weewx_data`, `on_mqtt_connect`, `on_mqtt_message`, `mqtt_publish`,
`on_mqtt_publish`, `update_record`.
`mqtt_publish` runs `immediate` before the send and `delay` after, with `mid`/`rc`.
A plugin may also implement an optional `shutdown()`.
See `docs/plugin-development/` for parameter meanings.

## Testing conventions and quirks

- Tests use the standalone `mock` package (not `unittest.mock`).
- Shared fixtures: `helpers.py` (`random_string`, `run_tests`), `mqttstubs.py` (paho stubs),
  `publisherbase.py` (`PublisherBase`, `TLSBase` — parameterized by `api` and
  `protocol_string`). Concrete publisher test files end with `del PublisherBase, TLSBase` so
  pytest doesn't collect the abstract bases (their tests `raise NotImplementedError`).
- `test_template.py` is the starting point for a new test file. Tests run under pytest *and*
  directly via the file's `helpers.run_tests()`.

## Config, versioning and release

- **New config options need two edits**: the template in `install.py` (`MQTTPUBLISH_CONFIG`)
  and the reference in `docs/common-options/index.md`. Deprecated options get an error/log
  message in `mqttpublish.py` and a page under `docs/deprecated-options/`.
- **VERSION is duplicated** in `install.py` and `bin/user/mqttpublish.py`; bump both.
- `changes.txt` is the changelog.
- Releases are tagged by `.github/workflows/versioning.yml` (Actions-Us/actions-tagger) on
  GitHub release publish.

## CI

- `.github/workflows/run-analyze-test.yml` (any non-master push) and
  `run-analyze-test-matrix.yml` (master pushes) both delegate to reusable workflows in
  `weewx-extensions/development-tools@v6`. The `module-name: 'mqttpublish'` input selects the
  module under test.
- The master matrix covers Python 3.9.13–3.14 and WeeWX 5.0.0 / 5.5.2 / branch-master /
  branch-development — so code must stay compatible with Python 3.9 syntax.
- **CI lint covers every module and the tests, and fails the build**: the workflows pass
  `lint-paths` with all module paths (including `mqttmessagetracker.py`, `mqttresend.py` and
  `mqttprune.py`), the reusable workflow lints `bin/user/tests` with `.pylintrc-tests`, and
  `lint-fail` defaults to true, so any pylint or flake8 finding turns the job red. Run
  `verify.sh` before committing.

## Cross-repo workflow

Single changes stay in this repository. Cross-repo work (a shared change, rename, wording pass)
starts in the workspace root (`weewx-mqtt`): see the workspace `AGENTS.md` for the order of a
cross-repo change and `./status-all.sh` to see every repository's state at once.
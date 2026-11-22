# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.0.0] - Draft

### Fixed

- Fixes to multiprocessing implementation
  - 'multiprocess' works on macOS. The worker is forked there instead of spawned, and a queue
    size that the platform cannot report is logged as 'unknown'.
  - Random locks/ stalls when reading from the multiprocessing data queue (#39).
  - Do not hang WeeWX on exit when the multiprocessing publishing worker does not stop.
  - Report a multiprocessing publishing worker that exits, with its exit code, instead of
    silently feeding records to a worker that is not picklable.
  - Use the fork start method explicitly for the publishing sub-process.
    Python 3.14 makes 'forkserver' the default on Linux, which pickles the process object and
   fails because the worker is handed objects that are not picklable.
  - Stop the publishing sub-process stalling when WeeWX logs from inside it.
  - Ensure the queue 'loop' method is called even when no data is waiting, by giving the
    data queue get() a configurable timeout.
  - Check the return code in the on_connect callback so failed connections are handled.
  - Compare the redundant/duplicate suppression threshold against the unformatted value.
  - Handle None values when applying the redundant/duplicate suppression threshold.
  - TLS 1.2 works on builds that no longer provide the legacy 'PROTOCOL_TLSv1_2' constant,
    such as one built against OpenSSL 4. An unavailable 'tls_version' is now reported as invalid
    instead of raising a KeyError.
  - MQTTConfigHA now ensures published values use WeeWX units.

### Enhancements

- Added a wait_for_inflight option, so shutdown can wait for paho to confirm in-flight messages.
- Improved shutdown logic flow, with timeouts when stopping threads/processes.

  - Improved logging
    - Connection lifecycle messages use the shared wording: 'Connecting to host:port.',
      'Connected with result code ..., ...', 'Subscribing to topic, mid ..., result code ...',
      and 'Subscribing to topic, mid ..., result code ...'.
    - Error and validation messages use the shared wording: 'Unable to ...: ...',
      'Invalid <thing>, <value>.', and one trailing period.
    - Deprecation messages use the shared wording ('<option> is deprecated, use <replacement>.',
      '<option> is deprecated, it is no longer used.'), with one trailing period and correct
      spacing.
    - Log messages use consistent terminology and spelling ('qos', 'database'), and the publish
      timing line no longer contains a double space.
    - Log the startup environment (version, WeeWX version, Python, platform, locale, paho.mqtt,
      logging settings, and record augmentation/generation) through the shared 'log_environment'
      block, using the 'Label: value.' format.
    - Configuration diagnostics use the 'Label: value.' format with one trailing period:
      'Sanitized configuration (removed: password): ...', 'Plugins: [...]', 'Loop topics: ...',
      and 'Archive topics: ...'. The mqtt configuration is logged the same way, and the topics are
      now logged once instead of twice.
    - The Logger now owns the log queue and the logging thread. Shutting down flushes queued log
      messages, is safe to call more than once, and no longer stalls process exit if it was skipped.
    - Log line prefixes use the format converged across the weewx-mqtt extensions, defined by the
      shared 'user.mqttcommon': (component-thread_id-archive_timestamp).
    - Consistent shutdown log messages
    - Align the logging call style with the subscribe extension. Logger.trace/debug/info/error take a
      message id (publish has no message ids, so all current messages pass None), and every log queue
      entry is built by Logger.create_entry, which adds msg_id and the emitting thread's thread_id.
      Log output is unchanged.
  - Plugin improvements
    - Added an on_publish plugin callback, and the monitor_on_publish option to monitor its execution time.
    - Added a mqtt_publish plugin callback. The immediate timing runs before the message is published,
      the delay timing runs after and provides the message id.
    - Plugins can optionally implement a shutdown method, called when the publishing thread stops.
    - Added an on_disconnect plugin callback, and the monitor_on_disconnect option to monitor
      its execution time.
    - A plugin can be loaded multiple times with different configurations.
    - The data queue size is passed into plugin callbacks.

Notes:

The following are deprecated and no longer used.
- [PublishWeeWX] was replaced by [MQTTPublish] (prior to V1).
- [MQTTPublish] / [[lwt]] has changed to [MQTTPublish] / [[availability_topic]].
  See, https://weewx-mqtt.github.io/publish/common-options/availability-topic.html
- [MQTTPublish] [[topics]] / [[[topic-name]]] / [[[[aggregates]]]] has been replaced witht plugin MQTTAggregateValues
  See, https://weewx-mqtt.github.io/publish/plugins/aggregatevalues/
- [MQTTPublish] max_retries, wait_between_retries, and wait_for_connection are deprecated and no longer used.
  Reconnection is handled by the paho mqtt network loop, configured with min_delay and max_delay.
  See, https://weewx-mqtt.github.io/publish/common-options/

Alpha release support for MessageTracker plugin, see https://weewx-mqtt.github.io/publish/plugins/messagetracker/

## [1.3.0]

### Fixed

- MQTTConfigHA no longer 'advertises' an availability topic when MQTTPublish is not publishing to it.

### Enhancements

- Support additional data types when publishing 'individual' topics.
- Empty the data queue as part of shutting down. This speeds up shut down when the queue has grown.
- Limit the publishing of redundant/duplicate data (#27).
- Move plugin config to top level (#32).
- Ability to configure a default value for all components belonging to a device (#33).
- Renamed the [[lwt]] section of MQTTPublish to [[availability_topic]]
- Options to monitor queue processing, see https://weewx-mqtt.github.io/publish/common-options/#monitor_queue

  For help migrating from 1.2.0 and prior see, https://weewx-mqtt.github.io/publish/upgradeguides/from120/

Alpha release support for ArchiveValues plugin, see https://weewx-mqtt.github.io/publish/plugins/archivevalues/
Alpha release support for running the publishing code in a separate process, see https://weewx-mqtt.github.io/publish/common-options/#multiprocess

## [1.2.0]

### Enhancements

- Added `publish_fields` option.
- Added more 'examples' to the configuration section that is 'installed' into weewx.conf.

## [1.1.0]

### Fixes

- Correct handling of conversion_type and format_string options.
  Note: Now the default conversion_type is 'None', meaning no conversion is performed.
- Better handling of tls related default values.
- Support aggregate values
  Ability to configure the WeeWX database binding used to calculate aggregates. (#7)
  Support for specifying a WeeWX unit systemt to convert all observations to. (#8)
  When an observation has a unit specified, use that when appending to the observation name.
- Reconnect logic (#14)
- Allow shutdown when attempting to (re)connect (#14)
- Perform MQTT disconnect on shut down and send 'offline' message.

### Enhancements

- Use the week_start configuration option of the the `[station]` when calculating week aggregates.
- Improvements when running in 'standalone mode'.
- Ability to configure how long to wait between connection attemps (#14)
- Ability to configure the maximum attempts to start the publishing thread (#14)
- Ability to configure how long to wait for data to be in data processing queue.
- Added `ignore_fields` option.
- Beta support for plugins to provide additional functions.
  Beta version of aggregate values has been moved to a plugin.
  Beta version of publishing Home Assistant MQTT Device Discovery messages.

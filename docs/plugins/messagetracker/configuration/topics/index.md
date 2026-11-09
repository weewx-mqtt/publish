---
title: topics
parent: Configuration
ancestor: MQTTMessageTracker
nav_order: 1
---
{% include messagetracker_warning.html %}

## The `[[topics]]` section

The topics to track. Only the topics listed here are tracked; a message published to any other
topic is not recorded. Required; when there is no enabled topic, the plugin logs an error and does
nothing.

A topic published with `qos = 0` is rejected: a qos 0 message is never acknowledged, so its
delivery cannot be confirmed and the tracker could only record it as if it had been. The plugin
logs an error and does not track that topic.

See [topic-name](topic-name/index.md) for the options of each topic.

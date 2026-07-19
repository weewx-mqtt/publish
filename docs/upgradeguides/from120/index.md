---
title: Upgrading from 1.2.0
parent: Upgrade Guides
nav_order: 1
---

Version 1.3.0 moved the configuration of the plugins MQTTAggregateValues and MQTTConfigHA to the 'top level' of the WeeWX configuration.
This is a breaking change for users of this beta functionality.

## Updating if you don't use the plugins

1. Make a backup of the WeeWX configuration.
2. Remove the [[plugins]] section and all of its subsections.
3. Install the desired version of MQTTPublish.
4. Restart WeeWX

## Updating for users of MQTTConfigHA

1. Make a backup of the WeeWX configuration.
2. Remove the [[plugins]] section and all of its subsections.
3. Install the desired version of MQTTPublish.
4. Look for the [MQTTConfigHA] section and migrate the [[plugins]] [[[MQTTHomeAssistantConfig]]] section to it.
    - This should only require removing two '[' from every section.
    So instead of [[[[devices]]]] it would be [[devices]].
    And so on...
5. Restart WeeWX

## Updating for users of MQTTAggregateValues

1. Make a backup of the WeeWX configuration.
2. Remove the [[plugins]] section and all of its subsections.
3. Install the desired version of MQTTPublish.
4. Look for the [MQTTAggregateValues] section and migrate the [[plugins]] [[[MQTTAggregateValues]]] section to it.
    - This should only require removing two '[' from every section.
    So instead of [[[[topics]]]] it would be [[topics]].
    And so on....
5. Restart WeeWX

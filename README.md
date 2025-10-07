# weewx-mqttpublish

## Description

A Weewx service publishes data to multiple MQTT topics.

Currently MQTT payloads of json, keyword (field1=value, field2=value..), and individual (each topic contains a single observation) are supported.

## Preqrequisites

|Prerequisite                                                   |Version                  |
|---------------------------------------------------------------|-------------------------|
|[WeeWX](https://www.weewx.com)                                 |5.0.0 or higher          |
|[Python](https://www.python.org)                               |3.9.13 or higher         |
|[Paho MQTT Python client](https://pypi.org/project/paho-mqtt/) |1.6.1 or higher          |
|[MQTT](https://mqtt.org)                                       |3.1, 3.1.1, 5 or higher. |

*Note:* Early versions of Python 3 may work, but have not been explicitly tested.

*Note:* Not all 'supported' versions of the Paho MQTT client have been tested.

*Note:* Not all 'supported' versions of MQTT have been tested.

## Installation

This extension is installed using the [weectl extension utility](https://www.weewx.com/docs/5.0/utilities/weectl-extension/).

The latest release can be installed with the invocation

```weectl extension install https://github.com/weewx-mqtt/publish/archive/refs/tags/latest.zip```.

If a specific version is desired, the invocation would look like `weectl extension install https://github.com/weewx-mqtt/publish/archive/refs/tags/vX.Y.Z.zip`-rc01.zip`; where X.Y.Z is the release.
The list of releases can be found here, [https://github.com/weewx-mqtt/publish/releases](https://github.com/weewx-mqtt/publish/releases).

The version under development can be installed from the master branch.
The invocation is, `weectl extension install https://github.com/weewx-mqtt/publish/archive/master.zip`,

### WeeWX package install

some note about having to logout/login for group update to take affect...

### WeeWX pip install

## Customizing

## Getting Help

Feel free to [open an issue](https://github.com/weewx-mqtt/publish/issues/new),
[start a discussion in github](https://github.com/weewx-mqtt/publish/discussions/new),
or [post on WeeWX google group](https://groups.google.com/g/weewx-user).
When doing so, see [Help! Posting to weewx user](https://github.com/weewx/weewx/wiki/Help!-Posting-to-weewx-user)
for information on capturing the log.
And yes, **capturing the log from WeeWX startup** makes debugging much easeier.

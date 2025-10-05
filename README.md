# weewx-mqttpublish

## Description

A Weewx service publishes data to multiple MQTT topics.

Currently MQTT payloads of json, keyword (field1=value, field2=value..), and individual (each topic contains a single observation) are supported.

## Prerequisites

* Python 3.9 or higher
  Note: Early versions of Python 3 may work, but have not been explicitly tested.
* WeeWX 5.0 or higher
* [Paho MQTT Python client](https://pypi.org/project/paho-mqtt/)

## Installation notes

Because there are [multiple methods to install WeeWX](http://weewx.com/docs/usersguide.htm#installation_methods), location of files can vary.
See [where to find things](http://weewx.com/docs/usersguide.htm#Where_to_find_things)
in the WeeWX [User's Guide](http://weewx.com/docs/usersguide.htm") for the definitive information.
The following symbolic names are used to define the various locations:

* *$DOWNLOAD_ROOT* - The directory containing the downloaded *weewx-aqi-xtype* extension.
* *$BIN_ROOT* - The directory where WeeWX executables are located.
* *$CONFIG_ROOT* - The directory where the configuration (typically, weewx.conf) is located.

The notation vX.Y.Z designates the version being installed.
X.Y.Z is the release.

Prior to making any updates/changes, always make a backup.

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

## Customizing

## Getting Help

Feel free to [open an issue](https://github.com/weewx-mqtt/publish/issues/new),
[start a discussion in github](https://github.com/weewx-mqtt/publish/discussions/new),
or [post on WeeWX google group](https://groups.google.com/g/weewx-user).
When doing so, see [Help! Posting to weewx user](https://github.com/weewx/weewx/wiki/Help!-Posting-to-weewx-user)
for information on capturing the log.
And yes, **capturing the log from WeeWX startup** makes debugging much easeier.

---
title: WeeWX-Publish
parent: Home Page
nav_order: 1
---

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

```shell
weectl extension install https://github.com/weewx-mqtt/publish/archive/refs/tags/latest.zip
```

If a specific version is desired, the invocation would look like

```shell
weectl extension install https://github.com/weewx-mqtt/publish/archive/refs/tags/vX.Y.Z.zip
```

where X.Y.Z is the release.
The list of releases can be found at [https://github.com/weewx-mqtt/publish/releases](https://github.com/weewx-mqtt/publish/releases).

The version under development can be installed from the master branch using the following invocation

```shell
weectl extension install https://github.com/weewx-mqtt/publish/archive/master.zip
```

Where `master` is the branch name.

*Note:* WeeWX 'package' installs add the user that performed the install to the `weewx` group.
This means that this user should not need to use `sudo` to install the `weewx-mqtt/publish` extension.
**But** in order to for this update to the `weewx` group to take affect, the user has to have logged out/in at least once or use one of the other methods that can be found on the web

*Note:* WeeWX pip installs that install WeeWX into a `Python virtual environment`, must 'activate' the environment performing the install. A typical invocation would look like this.

```shell
source ~/weewx-venv/bin/activate
```

## Customizing

weewx=mqtt/publish is installed with it disabled. Setting flag, [enable = true](https://github.com/weewx-mqtt/publish/wiki/Common-Options#enable) and restarting WeeWX will start publishing MQTT data to the configured broker and topics.
The configuration options can be found [here](https://github.com/weewx-mqtt/publish/wiki/Common-Options).
The [host](https://github.com/weewx-mqtt/publish/wiki/Common-Options#host) and [topic(s)](https://github.com/weewx-mqtt/publish/wiki/Common-Options#topic-name-sections) to publish to usually need to be configured.

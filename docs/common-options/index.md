---
title: Configuring MQTTPublish
nav_order: 2
---

There are three major pieces to the MQTTPublish configuration.

## The `[MQTTPublish]` section

This configures the MQTT connection and any necessary WeeWX options.

### enable

Whether the service is enabled or not.
Valid values are `true` or `false`.
The default value is `true`.

### log_mqtt

Controls the MQTT logging.
Valid values are `true` or `false`.
The default value is `true`.

### max_retries

The maximum number of times to try to reconnect.
The default value is `5`.

### clientid

The clientid to connect with.
The default value is `MQTTPublish-xxxx`, where xxxx is a random number between 1000 and 9999.

### host

The MQTT server.
The default value is `localhost`.

### keepalive

Maximum period in seconds allowed between communications with the broker.
The default value is `60`.

### port

The port to connect to.
The default value is `1883`.

### protocol

The MQTT protocol to use.
Valid values are `MQTTv31`, `MQTTv311`, or `MQTTv5`.
The default value is `MQTTv311`.

### username

The username for broker authentication.
The default value is `None`.

### password

The password for broker authentication.
The default is `None`.

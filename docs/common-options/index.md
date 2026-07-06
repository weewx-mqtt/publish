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

### data_binding

The WeeWX data_binding to use when calculating aggregates.
The default value is `wx_binding`.

### log_mqtt

Controls the MQTT logging.
Valid values are `true` or `false`.
The default value is `true`.

### wait_for_queue_element

The number of seconds to wait for the queue to have data to be processed.
The default value is `5`.

### wait_for_connection

The number of seconds to wait for connection processing.
The default value is `1`.

### max_retries

The maximum number of times to try to reconnect.
If unable to connect within `max_retries`, the publishing thread will be shutdown.
The default value is `5`.

### wait_between_retries

The number of secconds to wait before trying to reconnect when there is a connection error.
The default is `5`.

### max_thread_restarts

The number of times to attempt to start the publishing thread.
When a thread is running a successful connection is established, it is reset to `0`.
The default is `2`.

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

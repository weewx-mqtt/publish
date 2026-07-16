---
title: Configuring MQTTPublish
nav_order: 1
---

There are three major pieces to the MQTTPublish configuration.

## The `[MQTTPublish]` section

### These are options that control MQTTPublish processing

#### data_binding

The WeeWX data_binding to use when calculating aggregates.
The default value is `wx_binding`.

#### enable

Whether the service is enabled or not.
Valid values are `true` or `false`.
The default value is `true`.

#### max_retries

The maximum number of times to try to reconnect.
If unable to connect within `max_retries`, the publishing thread will be shutdown.
The default value is `5`.

#### max_thread_restarts

The number of times to attempt to start the publishing thread.
When a thread is running a successful connection is established, it is reset to `0`.
The default is `2`.

#### wait_between_retries

The number of secconds to wait before trying to reconnect when there is a connection error.
The default is `5`.

#### wait_for_connection

The number of seconds to wait for connection processing.
The default value is `1`.

#### wait_for_queue_elemen

The number of seconds to wait for the queue to have data to be processed.
The default value is `5`.

### These are options that are used as default for [topic settings](topics/topic-name/index.md)

#### minimum_interval

When set, only data that has changed since the publication is published.
This is the minimum amount of time between publication of the 'full set' of data.
For example, if it is set to 5, then approximately every 5 minutes the 'full set' of data will be published.

#### qos

The QOS level to publish to.
The default value is `0`.

#### retain

The MQTT retain flag.
Valid values are `true` or `false`.
The default value is `false`.

##### suppression_threshold

Allows one to 'tune' if a value should be considered equal to the previous published value.
For example, if suppression_threshold = .5, then as long as the new value is greater than the previous value minus .5 and less than the previous value plus .5, it will not be published.
So, if it is set to 0, any change will cause the value to be published.

#### type

The format of the MQTT payload.
Valid values are `individual`, `json`, or `keyword`.
The default value is `json`.

#### These are options that are used as default for [field settings](topics/topic-name/fields/field-name/index.md)

#### append_unit_label

Controls if the Weewx unit label should be appended to the data being published.
Valid values are `true` or `false`.
The default value is ``true`.

#### conversion_type

The data type conversion to apply to the data being published.
The default value is `string`.

#### format_string

The formatting to apply to the data being published.
The default value is `None`.

#### round

The rounding to apply to the data being published.
It will only be applied to data type of `float`.
The default value is `None`.

### These are options that used by paho.mqtt client

#### clientid

The clientid to connect with.
The default value is `MQTTPublish-xxxx`, where xxxx is a random number between 1000 and 9999.

#### host

The MQTT server.
The default value is `localhost`.

#### keepalive

Maximum period in seconds allowed between communications with the broker.
The default value is `60`.

#### log_mqtt

Controls the MQTT logging.
Valid values are `true` or `false`.
The default value is `true`.

#### password

The password for broker authentication.
The default is `None`.

#### port

The port to connect to.
The default value is `1883`.

#### protocol

The MQTT protocol to use.
Valid values are `MQTTv31`, `MQTTv311`, or `MQTTv5`.
The default value is `MQTTv311`.

#### username

The username for broker authentication.
The default value is `None`.

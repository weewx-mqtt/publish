---
title: Introduction to configuring MQTTPublish
parent: Home Page
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

## The `[[tls]]` section

The TLS options that are passed to tls_set method of the MQTT client.
For additional information see,
[https://eclipse.org/paho/clients/python/docs/strptime-format-codes](https://eclipse.org/paho/clients/python/docs/strptime-format-codes)

### enable

Whether `tls` is enabled or not.
Valid values are `true` or `false`.
The default value is `true`.

### ca_certs

Path to the Certificate Authority certificate files that are to be treated as trusted by this client.

### certfile

The PEM encoded client certificate and private keys.
The default value is `None`.

### certs_required

The certificate requirements that the client imposes on the broker.
Valid values are `none`, `optional`, or `required`.
The default value is `required`.

### ciphers

The encryption ciphers that are allowable for this connection.
Specify `None` to use the defaults.
The default value is `None`.

### keyfile

The private keys.
The default value is `None`.

### tls_version

The version of the SSL/TLS protocol to be used.
Valid values are `sslv2`, `sslv23`, `sslv3`, `tls`, `tlsv1`, `tlsv11`, or `tlsv12`.
The default value is `tlsv12`.

## The `[[lwt]]` section

### enable

Whether LWT (Last Will and Testament) is enabled or not.
Valid values are `true` or `false`.
The default value is `true`.

### topic

The topic that the will message should be published on.
The default value is `status`.

### online_payload

The default value is `online`.

### offline_payload

The default value is `offline`.

### qos

The quality of service level to use for the will.
The default value is `0`.

### retain

If set to `true`, the will message will be set as the "last known good"/retained message for the topic.
Valid values are `true` or `false`.
The default value is `true`.

## The `[[topics]]` section

This has the the MQTT topics that are to be published to along with options used to control processing of the messages.

### [[[topic-name]]] sections

#### publish

Controls if the topic is published.
Valid values are `true` or `false`.
The default value is `true`.

#### type

The format of the MQTT payload.
Valid values are `individual`, `json`, or `keyword`.
The default value is `json`.

#### binding

The WeeWX event binding.
Valid values are `loop`, `archive`, or `loop, archive`.
The default value is `archive, loop`.

#### qos

The QOS level to publish to.
The default value is `0`.

#### retain

The MQTT retain flag.
Valid values are `true` or `false`.
The default value is `false`.

#### unit_system

The unit system for data published to this topic.
The default value is `US`.

#### [[[[fields]]]]

##### [[[[[field-name]]]]] sections

###### ignore

Controls if the field should be ignore (not published).
Valid values are `true` or `false`.
Default value is `false`.

###### name

The WeeWX name of the data to be published.
The default is the config section (field-name) value.

###### unit

The WeeWX unit to convert the data being published to.
Default value is `None`.

###### publish_none_value

Controls if data with a value of `None` should be published.
Valud values are `true` or `false`.
The default value is `false`.

###### append_unit_label

Controls if the Weewx unit label should be appended to the data being published.
Valid values are `true` or `false`.
The default value is ``true`.

###### conversion_type

The data type conversion to apply to the data being published.
The default value is `string`.

###### format_string

The formatting to apply to the data being published.
The default value is `%s`.

#### [[[[aggregates]]]]

The WeeWX aggregations to perform.

##### [[[[[aggregation-observation-name]]]]] sections

The name of the aggregated observation in the MQTT payload.
This can be any name.
For example: rainSumDay, outTempMinHour, etc.

###### enable

Whether the aggregated value is published or not.
Valid values are `true` or `false`.
The default value is `true`.

###### observation

The WeeWX observation to aggregate, rain, outTemp, etc,

###### aggregation

The type of aggregation to perform.
See, [https://www.weewx.com/docs/customizing.htm#aggregation_types](https://www.weewx.com/docs/customizing.htm#aggregation_types)

###### period

The time period over which the aggregation should occurr.
Valid values are `hour`, `day`, `week`, `month`, `year`, `yesterday`, `last24hours`, `last7days`, `last31days`, or `last366days`.

## Additional information

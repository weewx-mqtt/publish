---
title: Plugin Development
nav_order: 3
#nav_exclude: true
---
{% include plugins_warning.html %}

MQTTPublish has a framework to add functionality via 'plugins'.
Functions belonging to the  plugin can be called at specific steps in the MQTTPublish data processing pipeline.
Currently these steps support callouts:

1. on_weewx_data
2. on_connect
3. on_message
4. update_record

Each of these callouts can be called either before MQTTPublish does its processing or after.

## Callouts

### on_weewx_data

This is the step that processes WeeWX loop packets or archive records.
It is called with a single dictionary containg the following information.

- time_stamp: The timestamp for this data
- data_type: dentifies the origin of the data 'archive' or 'loop'
- data: The WeeWX archive record or loop packet.

### on_connect

This is the MQTT on_connect callback.
It is called with the following parameters.
The are the same paramters that the Paho MQTT client calls. the `on_connect` callback with.

- mqtt_client: the client instance for this callback
- userdata: the private user data as set in Client() or user_data_set()
- flags: response flags sent by the broker
- reason_code: the connection reason code received from the broken. In MQTT v5.0 it’s the reason code defined by the standard. In MQTT v3, the return code is converted to a reason code, see convert_connack_rc_to_reason_code(). ReasonCode may be compared to integer.
- properties: the MQTT v5.0 properties received from the broker. For MQTT v3.1 and v3.1.1 properties is not provided and an empty Properties object is always used.

### on_message

This is the MQTT on_message callback.
It is called with the following parameters.

- client: the client instance for this callback
- userdata: the private user data as set in Client() or user_data_set()
- msg: the received message. This is a class with members topic, payload, qos, retain.

### update_record

This is when the data to be published is manipulated by MQTTPublish.
It is called with the following parameters.

- mqtt_client: the client instance to be used when publising the message
- topic: The topic that the message should be published on.
- data: the message to be sent.
- qos: The quality of service level to use.
- retain: If set to true, the message will be set as the “last known good”/retained message for the topic.

## `__init__` signature

## Required methods

The plugin must implement the `get_callbacks` method.
This method takes no paramters.
It returns a list of callback definitions.
A callback definition is a dictionary whose name is the name of the callback.
It has two entries.

1. timing: It can be one of `immediate` or `delayed`. `immnediate` means the callback is invoked before MQTTPublishing processing. `delayed` means the callout is invoked after the MQTTPublish processing.
2. callback: The actual method to be invoked.

Here is an example `get_callbacks` method.

``` python
    def get_callbacks(self):
        """ The callbacks. """
        return [
            {
                'on_weewx_data': {
                    'timing': 'immediate',
                    'callback': self.on_weewx_data
                }
            },
            {
                'on_mqtt_connect': {
                    'timing': 'immediate',
                    'callback': self.on_mqtt_connect
                }
            },
            {
                'on_mqtt_message': {
                    'timing': 'immediate',
                    'callback': self.on_mqtt_message
                },
                'update_record': {
                    'timing': 'immediate',
                    'callback': self.update_record
                },
            },
        ]
```

## Required configuration information

The plugin must a section below the `[[plugins]]` configuration section.
The section name is the name of the plugin.

### module

This is set to the module name of the plugin.

### Plugin specific configuration data

Following the `module` setting, any settings for the plugin can be specified;
followed by any plugin specific sub-sections.

``` text
[MQTTPublish]
 .
 .
 .
    [[plugins]]
        [[[MQTTHomeAssistantConfig]]]
            module = user.mqtthaconfig

            << any configuration data that is specific for the plugin>>
```

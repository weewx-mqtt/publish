""" Installer for mqttpublish service.

To uninstall run
wee_extension --uninstall=mqttpublish
"""

from io import StringIO

import configobj

from weecfg.extension import ExtensionInstaller

VERSION = "1.0.0-rc02a"

MQTTPUBLISH_CONFIG = """
[MQTTPublish]
    # Whether the service is enabled or not.
    # Valid values: true or false
    # Default is true.
    enable = false

    # The maximum number of times to try to reconnect.
    # Default is 5.
    max_retries = 5

    # Controls the MQTT logging.
    # Default is false.
    log_mqtt = false

    # The clientid to connect with.
    # Default is MQTTPublish-xxxx.
    #    Where xxxx is a random number between 1000 and 9999.
    clientid =

    # The MQTT server.
    # Default is localhost.
    host = localhost

    # The port to connect to.
    # Default is 1883.
    port = 1883

    # The protocol to use
    # Valid values: MQTTv31, MQTTv311, MQTTv5
    # Default is MQTTv311,
    protocol = MQTTv311

    # Maximum period in seconds allowed between communications with the broker.
    # Default is 60.
    keepalive = 60

    # username for broker authentication.
    # Default is None.
    username = None

    # password for broker authentication.
    # Default is None.
    password = None

    # The TLS options that are passed to tls_set method of the MQTT client.
    # For additional information see, https://eclipse.org/paho/clients/python/docs/strptime-format-codes
    [[tls]]
        # Turn tls on and off.
        # Default is true.
        enable = false

        # Path to the Certificate Authority certificate files that are to be treated as trusted by this client.
        ca_certs =

        # The PEM encoded client certificate and private keys.
        # Default is None
        certfile = None

        # The certificate requirements that the client imposes on the broker.
        # Valid values: none, optional, required
        # Default is required,
        certs_required = required

        # The encryption ciphers that are allowable for this connection. Specify None to use the defaults
        # Default is None.
        ciphers = None

        # The private keys.
        # Default is None
        keyfile = None

        # The version of the SSL/TLS protocol to be used.
        # Valid values: sslv2, sslv23, sslv3, tls, tlsv1, tlsv11, tlsv12.
        # Default is tlsv12.
        tls_version = tlsv12

    [[lwt]]
        # Turn lwt on and off.
        # Default is true.
        enable = false

        # The topic that the will message should be published on.
        # Default is 'status'.
        topic = 'status'

        # Default is 'online'.
        online_payload ='online'

        # The message to send as a will.
        # Default is 'offline'.
        offline_payload = offline

        # he quality of service level to use for the will.
        # Default is 0
        qos = 0

        # If set to true, the will message will be set as the "last known good"/retained message for the topic.
        # The default is true.
        retain = true

    [[topics]]
        [[[REPLACE_ME]]]
            # Controls if the topic is published.
            # Default is true.
            publish = false

            # The format of the MQTT payload.
            # Currently support: individual, json, keyword
            # The default is 'json'
            type = json

            # The binding, loop or archive.
            # Default is 'archive, loop'.
            binding = archive, loop

            # The QOS level to publish to.
            # Default is 0
            qos = 0

            # The MQTT retain flag.
            # The default is False.
            retain = False

            # The unit system for data published to this topic.
            # The default is US.
            unit_system = US

            [[[[fields]]]]
                [[[[[REPLACE_ME]]]]]
                    # True if the field should not be published.
                    # Valid values: True, False.
                    # Default is  False
                    ignore = true

                    # The WeeWX name of the data to be published.
                    # Default is the config section name.
                    # name =

                    # The WeeWX unit to convert the data being published to.
                    # Default is None.
                    # unit =

                    # Controls if data with a value of 'None' should be published.
                    # The default is false.
                    publish_none_value = false

                    # Controls if the WeewX unit label should be append to the data being published.
                    # The default is true.
                    append_unit_label = true

                    # The data type conversion to apply to the data being published.
                    # The default is 'string'.
                    conversion_type = string

                    # The formatting to apply to the data being published.
                    # The default is '%s'.
                    format_string = %s

            # The aggregations to perform
            [[[[aggregates]]]]
                # The name of the observation in the MQTT payload.
                # This can be any name. For example: rainSumDay, outTempMinHour, etc
                [[[[[REPLACE_ME]]]]]
                    # Turn aggregates on and off.
                    # Default is true.
                    enable = false

                    # The WeeWX observation to aggregate, rain, outTemp, etc,
                    observation =

                    # The type of aggregation to perform.
                    # See, https://www.weewx.com/docs/customizing.htm#aggregation_types
                    aggregation =

                    # The time period over which the aggregation shoulf occurr.
                    # Valid values: hour, day, week, month, year, yesterday, last24hours, last7days, last31days, last366days
                    period =

"""

def loader():
    """ Load and return the extension installer. """
    return MQTTPublishInstaller()


class MQTTPublishInstaller(ExtensionInstaller):
    """ The extension installer. """
    def __init__(self):

        install_dict = {
            'version': VERSION,
            'name': 'MQTTPublish',
            # add a leading space, so that long versions does not run into the description
            'description': ' Publish WeeWX data to a MQTT broker.',
            'author': "Rich Bell",
            'author_email': "bellrichm@gmail.com",
            'files': [('bin/user', ['bin/user/mqttpublish.py'])]
        }

        mqttpublish_dict = configobj.ConfigObj(StringIO(MQTTPUBLISH_CONFIG))
        install_dict['config'] = mqttpublish_dict
        # ToDo: Better service group?
        install_dict['restful_services'] = 'user.mqttpublish.PublishWeeWX'

        super(MQTTPublishInstaller, self).__init__(install_dict)

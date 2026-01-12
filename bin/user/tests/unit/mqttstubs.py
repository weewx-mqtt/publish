#
#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
'''
Stubs of paho mqtt code used by MQTTSubscribe.
'''

# pylint: disable=missing-function-docstring
import contextlib

@contextlib.contextmanager
def patch(module, old, new):
    original = getattr(module, old)
    setattr(module, old, new)
    try:
        yield
    finally:
        setattr(module, old, original)

class ClientV1Stub:
    '''
    Stub the paho mqtt Client class.
    Used to test WeeWX/MQTTSubscribe without needeing mqtt.
    Methods below are the ones used by MQTTSubscribe.
    '''

    # callbacks
    def on_log(self, _client, _userdata, level, msg):
        raise NotImplementedError("Stub method 'on_log' is not set")

    def on_connect(self, _client, _userdata, flags, reason_code, properties=None):
        raise NotImplementedError("Stub method 'on_connect' is not set")

    def on_disconnect(self, _client, _userdata, flags_rc, reason_code=None, properties=None):
        raise NotImplementedError("Stub method 'on_disconnect' is not set")

    def on_publish(self, _client, _userdata, mid, reason_codes=None, properties=None):
        raise NotImplementedError("Stub method 'on_publish' is not set")

    def __init__(self, callback_api_version=None, protocol=None, client_id=None, userdata=None, clean_session=None):  # need to match pylint: disable=unused-argument
        self.userdata = userdata
        self.topic = None
        return

    def username_pw_set(self, username, password):  # need to match pylint: disable=unused-argument
        return

    def will_set(self, topic, payload, qos, retain):  # need to match pylint: disable=unused-argument
        return

    def reconnect(self):
        return

    def tls_set(self, ca_certs, certfile, keyfile, cert_reqs, tls_version, ciphers):  # need to match pylint: disable=unused-argument
        return

    def publish(self, topic, data, qos, retain):  # need to match pylint: disable=unused-argument
        return

    def reconnect_delay_set(self, min_delay=None, max_delay=None):  # need to match pylint: disable=unused-argument
        return

    def connect(self, _host, _port, _keepalive):  # need to match pylint: disable=unused-argument
        return

    def subscribe(self, topic, qos):  # need to match pylint: disable=unused-argument
        print("In Subscribe")
        self.topic = topic
        return (0, 0)

    def loop(self, timeout=0):  # need to match pylint: disable=unused-argument
        # ToDo: This can't really be hard coded here
        # Because on_loop is called in other places
        self.on_connect(self, self.userdata, 0, 0)

        return

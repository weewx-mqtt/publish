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

from collections import namedtuple

@contextlib.contextmanager
def patch(module, old, new):
    original = getattr(module, old)
    setattr(module, old, new)
    try:
        yield
    finally:
        setattr(module, old, original)

class ClientStub:
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

    def __init__(self,
                 callback_api_version=None,
                 protocol=None,  # need to match pylint: disable=unused-argument
                 client_id=None,  # need to match pylint: disable=unused-argument
                 userdata=None,
                 clean_session=None):  # need to match pylint: disable=unused-argument
        self.userdata = userdata
        self.topic = None
        self.callback_api_version = callback_api_version

        # Some variables that are only used for testing
        self.on_connect_call_count = 0
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

    def connect(self, host, port, keepalive, clean_start=None):  # need to match pylint: disable=unused-argument
        # default is to 'perform' a connection (call on_connect)
        self.connect_with_connection(host, port, keepalive, clean_start)
        return

    def subscribe(self, topic, qos):  # need to match pylint: disable=unused-argument
        self.topic = topic
        return (0, 0)

    def loop(self, timeout=0):  # need to match pylint: disable=unused-argument
        return

    # The following routines are used for testing only

    # used to 'override' the on_connect method and not 'perform' the connection (call on_connect)
    def connect_without_connection(self, host, port, keepalive, clean_start=None):  # need to match pylint: disable=unused-argument
        self.on_connect_call_count += 1
        return

    # used to 'override' the on_connect method and 'perform' the connection (call on_connect)
    def connect_with_connection(self, host, port, keepalive, clean_start=None):  # need to match pylint: disable=unused-argument
        self.on_connect_call_count += 1
        if self.callback_api_version is not None:  # self.callback_api_version.value == 2:
            reason_code_dict = {
                'value': 0
            }
            reason_code = namedtuple('reason_code', reason_code_dict.keys())(**reason_code_dict)

            self.on_connect(self, self.userdata, 0, reason_code, 0)
        else:
            self.on_connect(self, self.userdata, 0, 0)

        return

    # used to 'override' the on_connect method and raise an exceptioin
    def connect_exception_first_call(self, host, port, keepalive, clean_start=None):  # need to match pylint: disable=unused-argument
        self.on_connect_call_count += 1
        if self.on_connect_call_count == 1:
            raise ConnetExceptionTest()

    # used to 'override' the on_connect method and raise an exceptioin
    def connect_exception_subsequent_calls(self,
                                           host,  # need to match pylint: disable=unused-argument
                                           port,  # need to match pylint: disable=unused-argument
                                           keepalive,  # need to match pylint: disable=unused-argument
                                           clean_start=None):  # need to match pylint: disable=unused-argument
        self.on_connect_call_count += 1
        if self.on_connect_call_count > 1:
            raise ConnetExceptionTest()

class ConnetExceptionTest(Exception):
    ''' Test Connect Exception'''

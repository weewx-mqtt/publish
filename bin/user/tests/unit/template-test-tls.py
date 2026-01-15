class Testtls_configuration(unittest.TestCase):

    def test_missing_PROTOCOL_TLSv1_1(self):
        global mock_client
        tls_version = 'tlsv1_1'
        config_dict = {
            'message_callback': {},
            'tls': {
                'ca_certs': random_string(),
                'tls_version': tls_version
            },
            'topics': {
                random_string(): {}
            }
        }
        config = configobj.ConfigObj(config_dict)
        mock_logger = mock.Mock(spec=Logger)

        with mock.patch('user.mqttsubscribe.MessageCallbackProvider'):
            with mock.patch('user.mqttsubscribe.TopicManager'):
                mock_client = mock.Mock()
                try:
                    saved_version = ssl.PROTOCOL_TLSv1_1
                    del ssl.PROTOCOL_TLSv1_1
                except AttributeError:
                    saved_version = None
                with self.assertRaises(ValueError) as error:
                    MQTTSubscriberTest(config, mock_logger)
                if saved_version:
                    ssl.PROTOCOL_TLSv1_1 = saved_version
                self.assertEqual(error.exception.args[0], f"Invalid 'tls_version'., {tls_version}")

    def test_missing_PROTOCOL_TLSv1_2(self):
        global mock_client
        tls_version = 'tlsv1_2'
        config_dict = {
            'message_callback': {},
            'tls': {
                'ca_certs': random_string(),
                'tls_version': tls_version
            },
            'topics': {
                random_string(): {}
            }
        }
        config = configobj.ConfigObj(config_dict)
        mock_logger = mock.Mock(spec=Logger)

        with mock.patch('user.mqttsubscribe.MessageCallbackProvider'):
            with mock.patch('user.mqttsubscribe.TopicManager'):
                mock_client = mock.Mock()
                try:
                    saved_version = ssl.PROTOCOL_TLSv1_2
                    del ssl.PROTOCOL_TLSv1_2
                except AttributeError:
                    saved_version = None
                with self.assertRaises(ValueError) as error:
                    MQTTSubscriberTest(config, mock_logger)
                if saved_version:
                    ssl.PROTOCOL_TLSv1_2 = saved_version
                self.assertEqual(error.exception.args[0], f"Invalid 'tls_version'., {tls_version}")

    def test_missing_PROTOCOL_SSLv2(self):
        global mock_client
        tls_version = 'sslv2'
        config_dict = {
            'message_callback': {},
            'tls': {
                'ca_certs': random_string(),
                'tls_version': tls_version
            },
            'topics': {
                random_string(): {}
            }
        }
        config = configobj.ConfigObj(config_dict)
        mock_logger = mock.Mock(spec=Logger)

        with mock.patch('user.mqttsubscribe.MessageCallbackProvider'):
            with mock.patch('user.mqttsubscribe.TopicManager'):
                mock_client = mock.Mock()
                try:
                    saved_version = ssl.PROTOCOL_SSLv2
                    del ssl.PROTOCOL_SSLv2
                except AttributeError:
                    saved_version = None
                with self.assertRaises(ValueError) as error:
                    MQTTSubscriberTest(config, mock_logger)
                if saved_version:
                    ssl.PROTOCOL_SSLv2 = saved_version
                self.assertEqual(error.exception.args[0], f"Invalid 'tls_version'., {tls_version}")

    def test_missing_PROTOCOL_SSLv23(self):
        global mock_client
        tls_version = 'sslv23'
        config_dict = {
            'message_callback': {},
            'tls': {
                'ca_certs': random_string(),
                'tls_version': tls_version
            },
            'topics': {
                random_string(): {}
            }
        }
        config = configobj.ConfigObj(config_dict)
        mock_logger = mock.Mock(spec=Logger)

        with mock.patch('user.mqttsubscribe.MessageCallbackProvider'):
            with mock.patch('user.mqttsubscribe.TopicManager'):
                mock_client = mock.Mock()
                try:
                    saved_version = ssl.PROTOCOL_SSLv23
                    del ssl.PROTOCOL_SSLv23
                except AttributeError:
                    saved_version = None
                with self.assertRaises(ValueError) as error:
                    MQTTSubscriberTest(config, mock_logger)
                if saved_version:
                    ssl.PROTOCOL_SSLv23 = saved_version
                self.assertEqual(error.exception.args[0], f"Invalid 'tls_version'., {tls_version}")

    def test_missing_PROTOCOL_SSLv3(self):
        global mock_client
        tls_version = 'sslv3'
        config_dict = {
            'message_callback': {},

            'tls': {
                'ca_certs': random_string(),
                'tls_version': tls_version
            },
            'topics': {
                random_string(): {}
            }
        }
        config = configobj.ConfigObj(config_dict)
        mock_logger = mock.Mock(spec=Logger)

        with mock.patch('user.mqttsubscribe.MessageCallbackProvider'):
            with mock.patch('user.mqttsubscribe.TopicManager'):
                mock_client = mock.Mock()
                try:
                    saved_version = ssl.PROTOCOL_SSLv3
                    del ssl.PROTOCOL_SSLv3
                except AttributeError:
                    saved_version = None
                with self.assertRaises(ValueError) as error:
                    MQTTSubscriberTest(config, mock_logger)
                if saved_version:
                    ssl.PROTOCOL_SSLv3 = saved_version
                self.assertEqual(error.exception.args[0], f"Invalid 'tls_version'., {tls_version}")

    def test_invalid_certs_required(self):
        global mock_client
        certs_required = random_string()
        config_dict = {
            'message_callback': {},
            'tls': {
                'ca_certs': random_string(),
                'certs_required': certs_required
            },
            'topics': {
                random_string(): {}
            }
        }
        config = configobj.ConfigObj(config_dict)
        mock_logger = mock.Mock(spec=Logger)

        with mock.patch('user.mqttsubscribe.MessageCallbackProvider'):
            with mock.patch('user.mqttsubscribe.TopicManager'):
                mock_client = mock.Mock()
                try:
                    saved_version = ssl.PROTOCOL_SSLv3
                    del ssl.PROTOCOL_SSLv3
                except AttributeError:
                    saved_version = None
                with self.assertRaises(ValueError) as error:
                    MQTTSubscriberTest(config, mock_logger)
                if saved_version:
                    ssl.PROTOCOL_SSLv3 = saved_version
                self.assertEqual(error.exception.args[0], f"Invalid 'certs_required'., {certs_required}")

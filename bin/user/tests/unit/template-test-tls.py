class Testtls_configuration(unittest.TestCase):

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

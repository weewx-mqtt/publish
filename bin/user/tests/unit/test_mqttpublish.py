#    Copyright (c) 2025 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

import configobj
import importlib
import logging
import sys

import unittest
import mock

import user.mqttpublish

class TestDeprecatedOptions(unittest.TestCase):
    def test_PublishWeeWX_stanza_is_deprecated(self):
        print("start")

        mock_engine = mock.Mock()
        config_dict = {
            'MQTTPublish': {
                'PublishWeeWX': {
                    'topics': {}
                }
            }
        }
        config = configobj.ConfigObj(config_dict)
        logger = logging.getLogger('user.mqttpublish')
        # with mock.patch('user.mqttpublish.mqtt'):
        with mock.patch('user.mqttpublish.PublishWeeWXThread'):
            with mock.patch.object(logger, 'error') as mock_error:
                user.mqttpublish.MQTTPublish(mock_engine, config)
                mock_error.assert_called_once_with(
                    "'PublishWeeWX' is deprecated. Move options to top level, '[MQTTPublish]'.")

        print("end")

if __name__ == '__main__':
    filename = sys.argv[0].rsplit('/', 1)[-1]
    module_name = filename.split('.', 11)[0]
    module = importlib.import_module(module_name)

    test_class = getattr(module, sys.argv[1])

    test_suite = unittest.TestSuite()
    test_suite.addTest(test_class(sys.argv[2]))
    unittest.TextTestRunner().run(test_suite)

    # unittest.main(exit=False)

#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name
import queue
import unittest

import mock

import helpers

import user.mqttpublish

class TestLoggerThread(unittest.TestCase):
    def test_run(self):
        mock_logger = mock.Mock()
        log_queue = queue.Queue()

        SUT = user.mqttpublish.LoggerThread(mock_logger, log_queue)

        debug_message = {'name': helpers.random_string(), 'log_type': 'DEBUG', 'log_message': helpers.random_string()}
        info_message = {'name': helpers.random_string(), 'log_type': 'INFO', 'log_message': helpers.random_string()}
        error_message = {'name': helpers.random_string(), 'log_type': 'ERROR', 'log_message': helpers.random_string()}
        no_log_type_message = {'name': helpers.random_string(), 'log_type': None, 'log_message': helpers.random_string()}
        unknown_type_message = {'name': helpers.random_string(),
                                'log_type': helpers.random_string(),
                                'log_message': helpers.random_string()}

        log_queue.put(debug_message)
        log_queue.put(info_message)
        log_queue.put(error_message)
        log_queue.put(no_log_type_message)
        log_queue.put(unknown_type_message)
        log_queue.put(None)

        SUT.start()
        SUT.join(timeout=5)

        self.assertFalse(SUT.is_alive())
        mock_logger.logdbg.assert_any_call(debug_message['name'], debug_message['log_message'])
        mock_logger.logerr.assert_any_call(error_message['name'], error_message['log_message'])
        self.assertEqual(mock_logger.loginf.call_count, 3)
        mock_logger.loginf.assert_any_call(info_message['name'], info_message['log_message'])
        mock_logger.logerr.assert_any_call(SUT.name, unknown_type_message)

if __name__ == '__main__':
    helpers.run_tests()

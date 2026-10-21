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

        SUT = user.mqttpublish.LoggerThread(log_queue, mock_logger)

        debug_entry = {'name': helpers.random_string(), 'log_type': 'DEBUG', 'log_message': helpers.random_string()}
        no_log_type_entry = {'name': helpers.random_string(), 'log_type': None, 'log_message': helpers.random_string()}
        error_entry = {'name': helpers.random_string(), 'log_type': 'ERROR', 'log_message': helpers.random_string()}

        log_queue.put(debug_entry)
        log_queue.put(no_log_type_entry)
        log_queue.put(error_entry)
        log_queue.put(None)

        SUT.start()
        SUT.join(timeout=5)

        self.assertFalse(SUT.is_alive())
        self.assertTrue(SUT.daemon)
        self.assertTrue(SUT.name.startswith('LoggerThread-'))

        entries = [call[0][0] for call in mock_logger.log_entry.call_args_list]
        self.assertEqual(len(entries), 5)
        self.assertEqual(entries[0], {'name': SUT.name, 'log_type': 'INFO', 'log_message': "Starting logger thread"})
        self.assertIs(entries[1], debug_entry)
        self.assertIs(entries[2], no_log_type_entry)
        self.assertIs(entries[3], error_entry)
        self.assertEqual(entries[4], {'name': SUT.name, 'log_type': 'INFO',
                                      'log_message': f"Exited logger thread, {SUT.name}."})

    def test_run_invalid_entry(self):
        mock_logger = mock.Mock()
        log_queue = queue.Queue()

        invalid_entry = {'name': helpers.random_string(), 'log_type': helpers.random_string(),
                         'log_message': helpers.random_string()}

        def log_entry(entry):
            if entry is invalid_entry:
                raise KeyError('log_type')

        mock_logger.log_entry.side_effect = log_entry

        SUT = user.mqttpublish.LoggerThread(log_queue, mock_logger)

        log_queue.put(invalid_entry)
        log_queue.put(None)

        SUT.start()
        SUT.join(timeout=5)

        self.assertFalse(SUT.is_alive())

        entries = [call[0][0] for call in mock_logger.log_entry.call_args_list]
        self.assertEqual(len(entries), 4)
        self.assertIs(entries[1], invalid_entry)
        # The raw entry is handed over as the message of an error entry.
        self.assertEqual(entries[2], {'name': SUT.name, 'log_type': 'ERROR', 'log_message': invalid_entry})
        self.assertEqual(entries[3]['log_type'], 'INFO')
        self.assertEqual(entries[3]['log_message'], f"Exited logger thread, {SUT.name}.")

if __name__ == '__main__':
    helpers.run_tests()

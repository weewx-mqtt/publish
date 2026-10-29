#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=wrong-import-order
# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring
# pylint: disable=invalid-name
import queue
import threading
import unittest

import mock

import helpers

import user.mqttpublish

class TestInitialization(unittest.TestCase):
    def test_init_starts_a_daemon_logger_thread(self):
        with mock.patch('user.mqttcommon.logging') as mock_logging:
            mock_log = mock_logging.getLogger.return_value
            log_queue = queue.Queue()
            name = helpers.random_string()

            SUT = user.mqttcommon.Logger({'name': name, 'log_queue': log_queue})

            self.assertEqual(SUT.name, name)
            self.assertIs(SUT.log_queue, log_queue)
            self.assertTrue(SUT.log_thread.daemon)
            self.assertTrue(SUT.log_thread.is_alive())

            SUT.shutdown(timeout=5)

            self.assertFalse(SUT.log_thread.is_alive())
            # The thread logs its start and its exit, and nothing else.
            messages = [call[0][2] for call in mock_log.info.call_args_list]
            self.assertEqual(messages, ["Starting logger thread.", "Exited logger thread."])

class TestCreateEntry(unittest.TestCase):
    def test_create_entry_captures_the_emitting_thread(self):
        name = helpers.random_string()
        text = helpers.random_string()

        entry = user.mqttcommon.Logger.create_entry(name, 'INFO', None, text)

        self.assertEqual(entry, {'name': name, 'log_type': 'INFO', 'msg_id': None, 'msg_text': text,
                                 'thread_id': threading.get_native_id(), 'archive_timestamp': None})

class TestQueueMethods(unittest.TestCase):
    def test_queue_methods_create_the_expected_entries(self):
        with mock.patch('user.mqttcommon.logging'):
            name = helpers.random_string()
            texts = [helpers.random_string() for _ in range(4)]
            SUT = user.mqttcommon.Logger({'name': name, 'log_queue': queue.Queue()})
            # Drain the thread so the entries stay queued for assertion.
            SUT.shutdown(timeout=5)

            SUT.trace(1, texts[0])
            SUT.debug(2, texts[1])
            SUT.info(3, texts[2])
            SUT.error(4, texts[3])

        entries = []
        while not SUT.log_queue.empty():
            entries.append(SUT.log_queue.get_nowait())

        self.assertEqual([entry['name'] for entry in entries], [name] * 4)
        self.assertEqual([entry['log_type'] for entry in entries], ['TRACE', 'DEBUG', 'INFO', 'ERROR'])
        self.assertEqual([entry['msg_id'] for entry in entries], [1, 2, 3, 4])
        self.assertEqual([entry['msg_text'] for entry in entries], texts)
        self.assertEqual([entry['thread_id'] for entry in entries], [threading.get_native_id()] * 4)

class TestLogEntry(unittest.TestCase):
    @staticmethod
    def _stopped_logger(name=None, log_queue=None):
        """ Construct a Logger and drain its thread, so log_entry calls are synchronous. """
        logger = user.mqttcommon.Logger({'name': name or helpers.random_string(),
                                         'log_queue': log_queue if log_queue is not None else queue.Queue()})
        logger.shutdown(timeout=5)
        return logger

    def test_log_entry_dispatches_the_log_types(self):
        with mock.patch('user.mqttcommon.logging') as mock_logging:
            mock_log = mock_logging.getLogger.return_value
            SUT = self._stopped_logger()
            mock_log.reset_mock()

            trace_name = helpers.random_string()
            trace_message = helpers.random_string()
            debug_name = helpers.random_string()
            debug_message = helpers.random_string()
            info_name = helpers.random_string()
            info_message = helpers.random_string()
            error_name = helpers.random_string()
            error_message = helpers.random_string()

            # Entries go through create_entry, as production sites do: the name plus the
            # queueing thread's id render in the prefix (no archive record is stamped).
            SUT.log_entry(user.mqttcommon.Logger.create_entry(trace_name, 'TRACE', None, trace_message))
            SUT.log_entry(user.mqttcommon.Logger.create_entry(debug_name, 'DEBUG', None, debug_message))
            SUT.log_entry(user.mqttcommon.Logger.create_entry(info_name, 'INFO', None, info_message))
            SUT.log_entry(user.mqttcommon.Logger.create_entry(error_name, 'ERROR', None, error_message))

            thread_prefix = f"-{threading.get_native_id()}"
            self.assertEqual(mock_log.debug.call_count, 2)
            mock_log.debug.assert_any_call("(%s) %s", f"{trace_name}{thread_prefix}", trace_message)
            mock_log.debug.assert_any_call("(%s) %s", f"{debug_name}{thread_prefix}", debug_message)
            mock_log.info.assert_called_once_with("(%s) %s", f"{info_name}{thread_prefix}", info_message)
            mock_log.error.assert_called_once_with("(%s) %s", f"{error_name}{thread_prefix}", error_message)

    def test_log_entry_with_no_log_type_is_skipped(self):
        with mock.patch('user.mqttcommon.logging') as mock_logging:
            mock_log = mock_logging.getLogger.return_value
            SUT = self._stopped_logger()
            mock_log.reset_mock()

            SUT.log_entry({'name': helpers.random_string(), 'log_type': None, 'msg_text': helpers.random_string()})

            mock_log.debug.assert_not_called()
            mock_log.info.assert_not_called()
            mock_log.error.assert_not_called()

    def test_log_entry_with_an_invalid_entry_raises(self):
        with mock.patch('user.mqttcommon.logging'):
            SUT = self._stopped_logger()

            with self.assertRaises(KeyError):  # unknown log type
                SUT.log_entry({'name': helpers.random_string(), 'log_type': helpers.random_string(),
                               'msg_text': helpers.random_string()})
            with self.assertRaises(KeyError):  # missing log type
                SUT.log_entry({})
            with self.assertRaises(TypeError):  # not a dict
                SUT.log_entry(helpers.random_string())

class TestShutdown(unittest.TestCase):
    def test_shutdown_drains_the_queue(self):
        with mock.patch('user.mqttcommon.logging') as mock_logging:
            mock_log = mock_logging.getLogger.return_value
            SUT = user.mqttcommon.Logger({'name': helpers.random_string(), 'log_queue': queue.Queue()})

            first = user.mqttcommon.Logger.create_entry(helpers.random_string(), 'INFO', None, helpers.random_string())
            second = user.mqttcommon.Logger.create_entry(helpers.random_string(), 'ERROR', None, helpers.random_string())
            SUT.log_queue.put(first)
            SUT.log_queue.put(second)

            SUT.shutdown(timeout=5)

            # The start message, the queued messages, and the exit message are logged in queue order.
            self.assertFalse(SUT.log_thread.is_alive())
            logged = [(call[0], call[1][2]) for call in mock_log.method_calls if call[0] in ('info', 'error')]
            self.assertEqual(logged, [('info', "Starting logger thread."),
                                      ('info', first['msg_text']),
                                      ('error', second['msg_text']),
                                      ('info', "Exited logger thread.")])

    def test_shutdown_is_idempotent(self):
        with mock.patch('user.mqttcommon.logging') as mock_logging:
            mock_log = mock_logging.getLogger.return_value
            SUT = user.mqttcommon.Logger({'name': helpers.random_string(), 'log_queue': queue.Queue()})

            SUT.shutdown(timeout=5)
            leftover = {'name': helpers.random_string(), 'log_type': 'INFO', 'msg_text': helpers.random_string()}
            SUT.log_queue.put(leftover)

            SUT.shutdown(timeout=5)

            # The second shutdown neither joins again nor queues another sentinel.
            self.assertFalse(SUT.log_thread.is_alive())
            self.assertIs(SUT.log_queue.get_nowait(), leftover)
            with self.assertRaises(queue.Empty):
                SUT.log_queue.get_nowait()
            mock_log.error.assert_not_called()

    def test_shutdown_warns_when_the_logger_thread_does_not_shut_down(self):
        with mock.patch('user.mqttcommon.logging') as mock_logging:
            mock_log = mock_logging.getLogger.return_value
            name = helpers.random_string()
            SUT = user.mqttcommon.Logger({'name': name, 'log_queue': queue.Queue()})

            # Replace log_entry to simulate a stuck WeeWX log handler.
            block_entered = threading.Event()
            blocked = threading.Event()

            def block_entry(_entry):
                block_entered.set()
                blocked.wait(5)

            SUT.log_entry = block_entry

            SUT.log_queue.put(user.mqttcommon.Logger.create_entry(helpers.random_string(), 'INFO', None,
                                                                  helpers.random_string()))
            self.assertTrue(block_entered.wait(5))

            SUT.shutdown(timeout=0.05)

            expected = SUT.log_messages[124004].format(name=SUT.log_thread.name)
            mock_log.error.assert_called_once_with("(%s) %s", f"{name}-{threading.get_native_id()}", expected)
            self.assertTrue(SUT.log_thread.is_alive())

            # Release the thread and wait for it to exit.
            blocked.set()
            SUT.log_thread.join(timeout=5)
            self.assertFalse(SUT.log_thread.is_alive())

if __name__ == '__main__':
    helpers.run_tests()

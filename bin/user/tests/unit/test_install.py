#    Copyright (c) 2026 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#

# pylint: disable=missing-module-docstring, missing-class-docstring, missing-function-docstring

import importlib.util
import os
import unittest
from io import StringIO

import configobj

import helpers

INSTALL_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'install.py'))


def load_installer():
    """ Load install.py, which is not a module on the path. """
    spec = importlib.util.spec_from_file_location('mqttpublish_install', INSTALL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestInstallConfig(unittest.TestCase):
    def setUp(self):
        self.install = load_installer()
        self.config = configobj.ConfigObj(StringIO(self.install.MQTTPUBLISH_CONFIG))

    def test_tracker_binding_is_seeded(self):
        self.assertEqual(self.config['MQTTMessageTracker']['data_binding'], 'message_tracker_binding')
        self.assertEqual(self.config['DataBindings']['message_tracker_binding']['database'], 'message_tracker')

        database = self.config['Databases']['message_tracker']
        self.assertEqual(database['database_name'], 'mqtt_message_tracker.sdb')
        self.assertEqual(database['database_type'], 'SQLite')

    def test_tracker_topics_are_seeded(self):
        topics = self.config['MQTTMessageTracker']['topics']

        self.assertEqual(topics.sections, ['REPLACE_ME'])
        self.assertEqual(topics['REPLACE_ME']['enable'], 'false')
        self.assertNotIn('retention', topics['REPLACE_ME'])

    def test_files(self):
        files = self.install.MQTTPublishInstaller()['files'][0][1]

        self.assertIn('bin/user/mqttmessagetracker.py', files)
        self.assertIn('bin/user/mqttreplay.py', files)


if __name__ == '__main__':
    helpers.run_tests()

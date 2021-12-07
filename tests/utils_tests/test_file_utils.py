import os
import unittest

import pytest
from klat_connector import start_socket

from tests.chatbot_objects import MockBot

SERVER = os.environ.get('server', "2222.us")


@pytest.mark.timeout(timeout=300, method='signal')
class FileUtilsTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ["V4_BOT_GREETINGS_PATH"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mocks')
        os.environ["V4_BOT_SMALL_TALK_PATH"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mocks')
        cls.bot = MockBot(start_socket(SERVER, 8888), "Private", None, None, True)

    def test_get_base_nick(self):
        self.assertEqual(self.bot.base_nick, 'test_bot')

    def test_resolve_resource(self):
        extracted_data = self.bot.resolve_bot_resource(file_name='greetings.json')
        self.assertIsNotNone(extracted_data)
        self.assertEqual(extracted_data, ['Hello from V4 Bot'])
        extracted_data = self.bot.resolve_bot_resource(file_name='small_talk.json')
        self.assertIsNotNone(extracted_data)
        self.assertEqual(extracted_data, {"Custom Topic": ["How was your day?"]})

    def test_small_talk(self):
        small_talk_response = self.bot.small_talk()
        self.assertIsNotNone(small_talk_response)
        self.assertEqual(small_talk_response, "How was your day?")

    def test_greetings(self):
        greetings_data = self.bot.greet()
        self.assertIsNotNone(greetings_data)
        self.assertEqual(greetings_data, "Hello from V4 Bot")

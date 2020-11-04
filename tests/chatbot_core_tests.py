from datetime import datetime
import unittest
import sys
import os
import pytest
from time import sleep

from klat_connector import start_socket

# Required for pytest on GitHub
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from chatbot_core import ChatBot, ConversationControls, ConversationState

bot = ChatBot(start_socket("2222.us"), "Private", "testrunner", "testpassword", True)
test_input = "prompt goes here"


class ChatbotCoreTests(unittest.TestCase):
    @pytest.mark.timeout(5)
    def test_01_initial_connection_settings(self):
        bot.bot_type = "submind"
        while not bot.ready:
            sleep(1)
        self.assertEqual(bot.nick, "testrunner")
        self.assertEqual(bot.logged_in, 2)

    @pytest.mark.timeout(5)
    def test_02_submind_response(self):
        self.assertEqual(bot.state, ConversationState.IDLE)
        bot.handle_incoming_shout("Proctor", f"testrunner {ConversationControls.RESP} "
                                             f"{test_input} (for 0 seconds).", bot._cid, bot._dom,
                                  datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(bot.active_prompt, test_input)
        self.assertEqual(bot.state, ConversationState.RESP)
        self.assertEqual(bot.chat_history[0][0], "testrunner", f"history={bot.chat_history}")
        self.assertEqual(bot.chat_history[0][1], test_input)
        self.assertEqual(len(bot.proposed_responses[test_input]), 0)

    @pytest.mark.timeout(5)
    def test_03_other_submind_responses(self):
        self.assertEqual(bot.state, ConversationState.RESP)
        bot.handle_incoming_shout("Other", "Other Bot Response.", bot._cid, bot._dom,
                                  datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(len(bot.proposed_responses[test_input]), 1)
        bot.handle_incoming_shout("Another", "Another Bot Response.", bot._cid, bot._dom,
                                  datetime.now().strftime("%I:%M:%S %p"))

        self.assertIn("Other", bot.proposed_responses[test_input].keys())
        self.assertIn("Other Bot Response.", bot.proposed_responses[test_input].values())

    @pytest.mark.timeout(5)
    def test_04_submind_discussion(self):
        bot.handle_incoming_shout("Proctor", f"{ConversationControls.DISC} 0 seconds.",
                                  bot._cid, bot._dom, datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(ConversationState.DISC, bot.state)

    @pytest.mark.timeout(5)
    def test_05_other_submind_discussion(self):
        self.assertEqual(bot.state, ConversationState.DISC)
        len_responses = len(bot.proposed_responses[test_input])
        bot.handle_incoming_shout("Other", "Other Bot Discussion.", bot._cid, bot._dom,
                                  datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(len(bot.proposed_responses[test_input]), len_responses, "Discussion counted as a response!")

    @pytest.mark.timeout(5)
    def test_06_submind_conversation_voting(self):
        bot.handle_incoming_shout("Proctor", f"{ConversationControls.VOTE} 0 seconds.",
                                  bot._cid, bot._dom, datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(ConversationState.VOTE, bot.state)

    @pytest.mark.timeout(5)
    def test_07_handle_votes(self):
        len_responses = len(bot.proposed_responses[test_input])
        self.assertEqual(bot.state, ConversationState.VOTE)
        bot.handle_incoming_shout("Other", "I vote for testrunner", bot._cid, bot._dom,
                                  datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(len(bot.proposed_responses[test_input]), len_responses, "Vote counted as a response!")

    @pytest.mark.timeout(5)
    def test_08_submind_conversation_pick(self):
        bot.handle_incoming_shout("Proctor", ConversationControls.PICK,
                                  bot._cid, bot._dom, datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(ConversationState.PICK, bot.state)

    @pytest.mark.timeout(5)
    def test_09_submind_conversation_idle(self):
        bot.handle_incoming_shout("Proctor", "The selected response is testrunner: \"test response\"",
                                  bot._cid, bot._dom, datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(ConversationState.IDLE, bot.state)
        self.assertEqual(bot.selected_history, ["testrunner"])
        self.assertEqual(bot.active_prompt, None)

    @pytest.mark.timeout(5)
    def test_10_shutdown_testing(self):
        bot.socket.disconnect()
        self.assertFalse(bot.socket.connected)


if __name__ == '__main__':
    unittest.main()

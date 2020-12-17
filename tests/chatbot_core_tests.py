from datetime import datetime
import unittest
import sys
import os
import pytest
import time

from klat_connector import start_socket

# Required for pytest on GitHub
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from chatbot_core import ChatBot, ConversationControls, ConversationState


class ChatbotCoreTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.bot = ChatBot(start_socket("2222.us"), "Private", "testrunner", "testpassword", True)
        cls.test_input = "prompt goes here"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.bot.socket.disconnect()

        if cls.bot.thread.isAlive():
            cls.bot.shout_queue.put(None)
            cls.bot.thread.join(0)

    @pytest.mark.timeout(10)
    def test_01_initial_connection_settings(self):
        self.bot.bot_type = "submind"
        while not self.bot.ready:
            time.sleep(1)
        self.assertEqual(self.bot.nick, "testrunner")
        self.assertEqual(self.bot.logged_in, 2)

    @pytest.mark.timeout(10)
    def test_02_submind_response(self):
        self.assertEqual(self.bot.state, ConversationState.IDLE)
        self.bot.handle_shout("Proctor", f"testrunner {ConversationControls.RESP} "
                                                  f"{self.test_input} (for 0 seconds).", self.bot._cid, self.bot._dom,
                                       datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(self.bot.active_prompt, self.test_input)
        self.assertEqual(self.bot.state, ConversationState.RESP)
        self.assertEqual(self.bot.chat_history[0][0], "testrunner", f"history={self.bot.chat_history}")
        self.assertEqual(self.bot.chat_history[0][1], self.test_input)
        self.assertEqual(len(self.bot.proposed_responses[self.test_input]), 0)

    @pytest.mark.timeout(10)
    def test_03_other_submind_responses(self):
        self.assertEqual(self.bot.state, ConversationState.RESP)
        self.bot.handle_shout("Other", "Other Bot Response.", self.bot._cid, self.bot._dom,
                                       datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(len(self.bot.proposed_responses[self.test_input]), 1)
        self.bot.handle_shout("Another", "Another Bot Response.", self.bot._cid, self.bot._dom,
                                       datetime.now().strftime("%I:%M:%S %p"))

        self.assertIn("Other", self.bot.proposed_responses[self.test_input].keys())
        self.assertIn("Other Bot Response.", self.bot.proposed_responses[self.test_input].values())

    @pytest.mark.timeout(10)
    def test_04_submind_discussion(self):
        self.bot.handle_shout("Proctor", f"{ConversationControls.DISC} 0 seconds.",
                                       self.bot._cid, self.bot._dom, datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(ConversationState.DISC, self.bot.state)

    @pytest.mark.timeout(10)
    def test_05_other_submind_discussion(self):
        self.assertEqual(self.bot.state, ConversationState.DISC)
        len_responses = len(self.bot.proposed_responses[self.test_input])
        self.bot.handle_shout("Other", "Other Bot Discussion.", self.bot._cid, self.bot._dom,
                                       datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(len(self.bot.proposed_responses[self.test_input]), len_responses,
                         "Discussion counted as a response!")

    @pytest.mark.timeout(10)
    def test_06_submind_conversation_voting(self):
        self.bot.handle_shout("Proctor", f"{ConversationControls.VOTE} 0 seconds.",
                                       self.bot._cid, self.bot._dom, datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(ConversationState.VOTE, self.bot.state)

    @pytest.mark.timeout(10)
    def test_07_handle_votes(self):
        len_responses = len(self.bot.proposed_responses[self.test_input])
        self.assertEqual(self.bot.state, ConversationState.VOTE)
        self.bot.handle_shout("Other", "I vote for testrunner", self.bot._cid, self.bot._dom,
                                       datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(len(self.bot.proposed_responses[self.test_input]), len_responses,
                         "Vote counted as a response!")

    @pytest.mark.timeout(10)
    def test_08_submind_conversation_pick(self):
        self.bot.handle_shout("Proctor", ConversationControls.PICK,
                                       self.bot._cid, self.bot._dom, datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(ConversationState.PICK, self.bot.state)

    @pytest.mark.timeout(10)
    def test_09_submind_conversation_idle(self):
        self.bot.handle_shout("Proctor", "The selected response is testrunner: \"test response\"",
                                       self.bot._cid, self.bot._dom, datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(ConversationState.IDLE, self.bot.state)
        self.assertEqual(self.bot.selected_history, ["testrunner"])
        self.assertEqual(self.bot.active_prompt, None)

    @pytest.mark.timeout(30)
    def test_10_login_register_new_user(self):
        self.bot.logout_klat()
        self.assertEqual(self.bot.logged_in, 1)
        username = f"testrunner{time.time()}".split(".")[0]
        self.bot.username = username
        self.bot.password = "testpassword"
        self.bot.login_klat(username, "testpassword")
        while not self.bot.enable_responses:
            time.sleep(1)
        self.assertEqual(self.bot.logged_in, 2)
        self.assertEqual(self.bot.username, username)

    @pytest.mark.timeout(10)
    def test_11_clean_options(self):
        self.bot.active_prompt = "Test Prompt"
        self.bot.proposed_responses[self.bot.active_prompt] = {self.bot.nick: "This is removed",
                                                               "Other User": "Valid Response",
                                                               "Removed User": "Test Prompt"}
        opts = self.bot._clean_options()
        self.assertIsInstance(opts, dict)
        self.assertNotIn(self.bot.nick, opts.keys())
        self.assertNotIn(self.bot.active_prompt, opts.values())

    @pytest.mark.timeout(10)
    def test_12_valid_add_to_queue(self):
        test_input = ("user", "shout", "cid", "dom", "timestamp")
        self.bot.handle_incoming_shout(test_input[0], test_input[1], test_input[2], test_input[3], test_input[4])
        queued = self.bot.shout_queue.get(timeout=2)
        self.assertEqual(queued, test_input)

    @pytest.mark.timeout(10)
    def test_13_add_none_to_queue(self):
        self.bot.shout_queue.put(None)
        time.sleep(3)
        self.assertTrue(self.bot.shout_queue.empty())
        self.assertFalse(self.bot.thread.isAlive())

    # @pytest.mark.timeout(10)
    # def test_12_shutdown_testing(self):
    #     self.bot.socket.disconnect()
    #     self.assertFalse(self.bot.socket.connected)

    # def test_bots_in_dir(self):
    #     from chatbot_core.utils import get_bots_in_dir
    #     get_bots_in_dir("/home/d_mcknight/PycharmProjects/chatbots/bots/ELIZA")

# TODO: Test CLI bot detection, credentials load, etc. DM


if __name__ == '__main__':
    unittest.main()

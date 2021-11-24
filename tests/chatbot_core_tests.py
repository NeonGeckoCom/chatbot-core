# NEON AI (TM) SOFTWARE, Software Development Kit & Application Development System
#
# Copyright 2008-2021 Neongecko.com Inc. | All Rights Reserved
#
# Notice of License - Duplicating this Notice of License near the start of any file containing
# a derivative of this software is a condition of license for this software.
# Friendly Licensing:
# No charge, open source royalty free use of the Neon AI software source and object is offered for
# educational users, noncommercial enthusiasts, Public Benefit Corporations (and LLCs) and
# Social Purpose Corporations (and LLCs). Developers can contact developers@neon.ai
# For commercial licensing, distribution of derivative works or redistribution please contact licenses@neon.ai
# Distributed on an "AS IS” basis without warranties or conditions of any kind, either express or implied.
# Trademarks of Neongecko: Neon AI(TM), Neon Assist (TM), Neon Communicator(TM), Klat(TM)
# Authors: Guy Daniels, Daniel McKnight, Regina Bloomstine, Elon Gasper, Richard Leeds
#
# Specialized conversational reconveyance options from Conversation Processing Intelligence Corp.
# US Patents 2008-2021: US7424516, US20140161250, US20140177813, US8638908, US8068604, US8553852, US10530923, US10530924
# China Patent: CN102017585  -  Europe Patent: EU2156652  -  Patents Pending

from datetime import datetime
import unittest
import sys
import os
import pytest
import time

from klat_connector import start_socket
from klat_connector.mach_server import MachKlatServer

# Required for pytest on GitHub
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from chatbot_core import ConversationControls, ConversationState
from chatbot_core.utils import clean_up_bot
from tests.chatbot_objects import *


SERVER = "0.0.0.0"


@pytest.mark.timeout(timeout=300, method='signal')
class ChatbotCoreTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.sio_server = MachKlatServer()
        cls.bot = ChatBot(start_socket(SERVER), "Private", "testrunner", "testpassword", True)
        cls.test_input = "prompt goes here"

    @classmethod
    def tearDownClass(cls) -> None:
        clean_up_bot(cls.bot)
        cls.sio_server.shutdown_server()

    @pytest.mark.timeout(10)
    def test_01_initial_connection_settings(self):
        self.bot.bot_type = "submind"
        self.bot.klat_ready.wait()
        self.assertEqual(self.bot.nick, "testrunner")
        self.assertEqual(self.bot.logged_in, 2)
        self.assertTrue(self.bot.socket.connected)

    @pytest.mark.timeout(10)
    def test_02_submind_response(self):
        self.assertEqual(self.bot.state, ConversationState.IDLE)
        self.bot.handle_shout("Proctor", f"testrunner {ConversationControls.RESP} "
                                         f"{self.test_input} (for 0 seconds).", self.bot._cid, self.bot._dom,
                              datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(self.bot.active_prompt, self.test_input)
        LOG.info(self.bot._user_is_proctor(self.bot.nick))
        self.assertEqual(self.bot.state, ConversationState.RESP)
        self.assertEqual(self.bot.request_history[0][0], "testrunner", f"history={self.bot.request_history}")
        self.assertEqual(self.bot.request_history[0][1], self.test_input)
        self.assertEqual(len(self.bot.proposed_responses[self.test_input]), 0)

    @pytest.mark.timeout(10)
    def test_03_other_submind_responses(self):
        self.assertEqual(self.bot.state, ConversationState.RESP)
        self.bot.handle_shout("Other", "Other Bot Response.", self.bot._cid, self.bot._dom,
                              datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(len(self.bot.proposed_responses[self.test_input]), 1)
        self.bot.handle_shout("Another", "Another Bot Response.", self.bot._cid, self.bot._dom,
                              datetime.now().strftime("%I:%M:%S %p"))
        self.assertIn("other", self.bot.proposed_responses[self.test_input].keys())
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

    # This is just testing a method in klat_api, not really a chatbot-core test
    # @pytest.mark.timeout(30)
    # def test_10_login_register_new_user(self):
    #     self.bot.logout_klat()
    #     self.assertEqual(self.bot.logged_in, 1)
    #     username = f"testrunner{time.time()}".split(".")[0]
    #     self.bot.username = username
    #     self.bot.password = "testpassword"
    #     self.bot.login_klat(username, "testpassword")
    #     while not self.bot.enable_responses:
    #         time.sleep(1)
    #     self.assertEqual(self.bot.logged_in, 2)
    #     self.assertEqual(self.bot.username, username)

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

    # @pytest.mark.timeout(10)
    # def test_13_add_none_to_queue(self):
    #     self.bot.shout_queue.put(None)
    #     time.sleep(3)
    #     self.assertTrue(self.bot.shout_queue.empty())
    #     self.assertFalse(self.bot.shout_thread.isAlive())

    @pytest.mark.timeout(10)
    def test_14_voting(self):
        self.bot.state = ConversationState.VOTE
        resp = self.bot.vote_response(self.bot.nick)
        self.assertEqual(resp, "abstain")

        resp = self.bot.vote_response("abstain")
        self.assertEqual(resp, "abstain")

        resp = self.bot.vote_response("")
        self.assertIsNone(resp)

        self.assertNotEqual(self.bot.nick, "someuser")
        resp = self.bot.vote_response("someuser")
        self.assertEqual(resp, "someuser")

    @pytest.mark.timeout(10)
    def test_15_histories_length(self):
        self.assertTrue(len(self.bot.request_history) == len(self.bot.participant_history))

    # @pytest.mark.timeout(10)
    # def test_12_shutdown_testing(self):
    #     self.bot.socket.disconnect()
    #     self.assertFalse(self.bot.socket.connected)

    # def test_bots_in_dir(self):
    #     from chatbot_core.utils import get_bots_in_dir
    #     get_bots_in_dir("/home/d_mcknight/PycharmProjects/chatbots/bots/ELIZA")

    @pytest.mark.timeout(30)
    def test_start_base_bot(self):
        from chatbot_core.utils.bot_utils import _start_bot
        from multiprocessing import Process, synchronize

        t, e = _start_bot(ChatBot, SERVER, 8888, "Private", "testrunner", "testpassword")
        self.assertIsInstance(t, Process)
        self.assertIsInstance(e, synchronize.Event)
        # self.assertFalse(e.is_set())
        e.set()
        timeout = time.time() + 10
        while e.is_set() and time.time() < timeout:
            print("...")
            time.sleep(2)
        self.assertFalse(e.is_set())
        t.terminate()
        self.assertFalse(t.is_alive())
        print("Joining...")
        t.join()

    @pytest.mark.timeout(30)
    def test_start_v2_bot(self):
        from chatbot_core.utils.bot_utils import _start_bot
        from multiprocessing import Process, synchronize

        t, e = _start_bot(V2Bot, SERVER, 8888, "Private", "testrunner", "testpassword")
        self.assertIsInstance(t, Process)
        self.assertIsInstance(e, synchronize.Event)
        # self.assertFalse(e.is_set())
        e.set()
        timeout = time.time() + 10
        while e.is_set() and time.time() < timeout:
            print("...")
            time.sleep(2)
        self.assertFalse(e.is_set())
        t.terminate()
        self.assertFalse(t.is_alive())
        print("Joining...")
        t.join()

    @pytest.mark.timeout(30)
    def test_start_v3_bot(self):
        from chatbot_core.utils.bot_utils import _start_bot
        from multiprocessing import Process, synchronize

        t, e = _start_bot(V3Bot, SERVER, 8888, "Private", "testrunner", "testpassword")
        self.assertIsInstance(t, Process)
        self.assertIsInstance(e, synchronize.Event)
        # self.assertFalse(e.is_set())
        e.set()
        timeout = time.time() + 10
        while e.is_set() and time.time() < timeout:
            print("...")
            time.sleep(2)
        self.assertFalse(e.is_set())
        t.terminate()
        self.assertFalse(t.is_alive())
        print("Joining...")
        t.join()

    @pytest.mark.timeout(30)
    def test_messagebus_connection(self):
        from chatbot_core.utils import init_message_bus
        from threading import Thread
        from mycroft_bus_client import MessageBusClient

        t, bus = init_message_bus()
        self.assertIsInstance(t, Thread)
        self.assertIsInstance(bus, MessageBusClient)
        self.assertTrue(bus.started_running)

        bus.close()
        t.join(5)

# TODO: Test CLI bot detection, credentials load, etc. DM


if __name__ == '__main__':
    unittest.main()

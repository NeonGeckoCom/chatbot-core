from datetime import datetime
import unittest
from time import sleep

from klat_connector import start_socket

from chatbot_core import ChatBot, ConversationControls, ConversationState

bot = ChatBot(start_socket("2222.us"), "chatbotsforum.org", "testrunner", "testpassword", True)


class ChatbotCoreTests(unittest.TestCase):
    def test_1_initial_connection_settings(self):
        bot.bot_type = "submind"
        while not bot.ready:
            sleep(1)
        self.assertEqual(bot.nick, "testrunner")
        self.assertEqual(bot.logged_in, 2)

    def test_2_submind_conversation_input(self):
        test_input = "input test"
        self.assertEqual(bot.state, ConversationState.IDLE)
        bot.handle_incoming_shout("Proctor", f"testrunner {ConversationControls.RESP} "
                                             f"{test_input} (for 0 seconds).", bot._cid, bot._dom,
                                  datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(bot.active_prompt, test_input)
        self.assertEqual(bot.state, ConversationState.RESP)
        self.assertEqual(bot.chat_history[0][0], "testrunner", f"history={bot.chat_history}")
        self.assertEqual(bot.chat_history[0][1], test_input)

    # TODO: Test bot responses here DM

    def test_3_submind_conversation_discussion(self):
        # bot.active_prompt = "input test"
        # bot.proposed_responses["input test"] = {}
        bot.handle_incoming_shout("Proctor", f"{ConversationControls.DISC} 0 seconds.",
                                  bot._cid, bot._dom, datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(ConversationState.DISC, bot.state)

    # TODO: Test bot conversation here DM

    def test_4_submind_conversation_voting(self):
        bot.handle_incoming_shout("Proctor", f"{ConversationControls.VOTE} 0 seconds.",
                                  bot._cid, bot._dom, datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(ConversationState.VOTE, bot.state)

    # TODO: Test bot votes here DM

    def test_5_submind_conversation_pick(self):
        bot.handle_incoming_shout("Proctor", ConversationControls.PICK,
                                  bot._cid, bot._dom, datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(ConversationState.PICK, bot.state)

    def test_6_submind_conversation_idle(self):
        bot.handle_incoming_shout("Proctor", "The selected response is testrunner: \"test response\"",
                                  bot._cid, bot._dom, datetime.now().strftime("%I:%M:%S %p"))
        self.assertEqual(ConversationState.IDLE, bot.state)
        self.assertEqual(bot.selected_history, ["testrunner"])


if __name__ == '__main__':
    unittest.main()

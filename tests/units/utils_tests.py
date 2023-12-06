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
import os
import unittest


class BotUtilsTests(unittest.TestCase):
    def test_start_bots(self):
        from chatbot_core.utils.bot_utils import start_bots
        # TODO

    def test_debug_bots(self):
        from chatbot_core.utils.bot_utils import debug_bots
        # TODO

    def test_clean_up_bot(self):
        from chatbot_core.utils.bot_utils import clean_up_bot
        # TODO

    def test_generate_random_response(self):
        from chatbot_core.utils.bot_utils import generate_random_response
        # TODO

    def test_find_closest_answer(self):
        from chatbot_core.utils.bot_utils import find_closest_answer
        # TODO

    def test_grammar_check(self):
        from chatbot_core.utils.bot_utils import grammar_check
        # TODO

    def test_find_bot_modules(self):
        from chatbot_core.utils.bot_utils import _find_bot_modules
        # TODO

    def test_run_mq_bot(self):
        from chatbot_core.utils.bot_utils import run_mq_bot
        # TODO


class CacheTests(unittest.TestCase):
    from chatbot_core.utils.cache import FIFOCache
    cache_size = 3
    cache = FIFOCache(capacity=cache_size)

    def test_init(self):
        from collections import OrderedDict
        self.assertIsInstance(self.cache.cache, OrderedDict)
        self.assertEqual(self.cache.capacity, self.cache_size)

    def test_put_get(self):
        num_put = 10
        for i in range(num_put):
            self.cache.put(str(i), str(i))
        self.assertEqual(len(self.cache.cache), self.cache.capacity)
        for i in range(num_put):
            if i < num_put - self.cache_size:
                self.assertIsNone(self.cache.get(str(i)), self.cache.cache)
            else:
                self.assertEqual(self.cache.get(str(i)), str(i),
                                 self.cache.cache)


class TestConversationUtils(unittest.TestCase):
    def test_create_conversation_cycle(self):
        from chatbot_core.utils.conversation_utils import create_conversation_cycle
        from chatbot_core.utils.enum import ConversationState
        convo = create_conversation_cycle()
        self.assertEqual(next(convo), ConversationState.RESP)
        self.assertEqual(next(convo), ConversationState.DISC)
        self.assertEqual(next(convo), ConversationState.VOTE)
        self.assertEqual(next(convo), ConversationState.PICK)
        self.assertEqual(next(convo), ConversationState.IDLE)
        self.assertEqual(next(convo), ConversationState.RESP)


class TestEnum(unittest.TestCase):
    def test_conversation_controls(self):
        from chatbot_core.utils.enum import ConversationControls
        for c in (ConversationControls.RESP, ConversationControls.DISC,
                  ConversationControls.VOTE, ConversationControls.PICK,
                  ConversationControls.NEXT, ConversationControls.HIST,
                  ConversationControls.WAIT):
            self.assertIsInstance(c, str)

    def test_conversation_state(self):
        from chatbot_core.utils.enum import ConversationState
        for state in ConversationState:
            self.assertIsInstance(state.value, int)

    def test_bot_types(self):
        from chatbot_core.utils.enum import BotTypes
        for b in (BotTypes.PROCTOR, BotTypes.SUBMIND, BotTypes.OBSERVER):
            self.assertIsInstance(b, str)

    def test_conversation_state_announcements(self):
        from chatbot_core.utils.enum import ConversationState, \
            CONVERSATION_STATE_ANNOUNCEMENTS
        for state in (ConversationState.RESP, ConversationState.DISC,
                      ConversationState.VOTE, ConversationState.PICK):
            self.assertIsInstance(CONVERSATION_STATE_ANNOUNCEMENTS[state], str)


class LoggerTests(unittest.TestCase):
    def test_make_logger(self):
        from chatbot_core.utils.logger import make_logger
        from ovos_utils.log import LOG

        # Simple named log
        log = make_logger("test")
        self.assertEqual(log, LOG)
        self.assertEqual(LOG.name, "test")

        # Named log with level override
        log = make_logger("test_2", "ERROR")
        self.assertEqual(log, LOG)
        self.assertEqual(LOG.name, "test_2")
        self.assertEqual(LOG.level, "ERROR")


class StringUtilsTests(unittest.TestCase):
    def test_remove_prefix(self):
        from chatbot_core.utils.string_utils import remove_prefix
        # TODO


class VersionUtilsTests(unittest.TestCase):
    def test_get_class(self):
        from chatbot_core.utils.version_utils import get_class
        from chatbot_core.v1 import ChatBot as V1
        from chatbot_core.v2 import ChatBot as V2

        # Explicit valid option
        os.environ["CHATBOT_VERSION"] = "v1"
        self.assertEqual(get_class(), V1)
        os.environ["CHATBOT_VERSION"] = "v2"
        self.assertEqual(get_class(), V2)

        # Default returns v1
        os.environ.pop("CHATBOT_VERSION")
        self.assertEqual(get_class(), V1)

        # Invalid config returns None
        os.environ["CHATBOT_VERSION"] = "0"
        self.assertIsNone(get_class())

if __name__ == '__main__':
    unittest.main()
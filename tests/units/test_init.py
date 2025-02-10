# NEON AI (TM) SOFTWARE, Software Development Kit & Application Development System
#
# Copyright 2008-2025 Neongecko.com Inc. | All Rights Reserved
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
from unittest.mock import patch


class ChatbotCoreTests(unittest.TestCase):
    def test_ChatBot_class(self):
        from chatbot_core.v1 import ChatBot as V1
        from chatbot_core.v2 import ChatBot as V2

        # Test valid v2 spec
        os.environ["CHATBOT_VERSION"] = "v2"
        from chatbot_core import ChatBot
        self.assertEqual(ChatBot, V2, "Expected v2")
        # sys.modules.pop("chatbot_core")

        # Test valid v1 spec
        os.environ["CHATBOT_VERSION"] = "v1"
        from chatbot_core import ChatBot
        self.assertEqual(ChatBot, V1, "Expected v1")
        # sys.modules.pop("chatbot_core")

        # Test default
        os.environ.pop("CHATBOT_VERSION")
        from chatbot_core import ChatBot
        self.assertEqual(ChatBot, V1, "Expected v1")

        # Test invalid
        os.environ["CHATBOT_VERSION"] = '3'
        from chatbot_core import ChatBot
        self.assertEqual(ChatBot, V1, "Expected v1")

    @patch("chatbot_core.utils.bot_utils.grammar_check")
    @patch("chatbot_core.utils.bot_utils.clean_up_bot")
    @patch("chatbot_core.utils.bot_utils.generate_random_response")
    def test_backwards_compat(self, random_response, clean_up, grammar):
        import chatbot_core

        from chatbot_core.utils.enum import ConversationControls
        self.assertEqual(chatbot_core.ConversationControls,
                         ConversationControls)

        from chatbot_core.utils.enum import ConversationState
        self.assertEqual(chatbot_core.ConversationState, ConversationState)

        random_response.assert_not_called()
        clean_up.assert_not_called()
        grammar.assert_not_called()

        chatbot_core.generate_random_response("one", test=1)
        random_response.assert_called_once_with("one", test=1)

        chatbot_core.clean_up_bot("two", test=2)
        clean_up.assert_called_once_with("two", test=2)

        chatbot_core.grammar_check("three", test=3)
        grammar.assert_called_once_with("three", test=3)


if __name__ == '__main__':
    unittest.main()

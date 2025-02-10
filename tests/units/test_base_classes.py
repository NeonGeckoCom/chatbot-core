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

import unittest
from logging import Logger

from unittest.mock import patch
from ovos_utils.log import LOG

from .mocks import MockMQ


class ChatBotV1Tests(unittest.TestCase):
    from klat_connector.mach_server import MachKlatServer
    from klat_connector import start_socket
    server = MachKlatServer()
    socket = start_socket(addr="0.0.0.0")

    @patch("chatbot_core.utils.bot_utils.clean_up_bot")
    def test_init(self, clean_up):
        from chatbot_core.chatbot_abc import ChatBotABC
        from chatbot_core.v1 import ChatBot

        domain = "test_domain"
        bot_kwargs = ChatBot(socket=self.socket, domain=domain,
                             username="test", password="pass", on_server=False,
                             is_prompter=False)
        self.assertIsInstance(bot_kwargs, ChatBotABC)
        self.assertEqual(bot_kwargs.socket, self.socket)
        self.assertEqual(bot_kwargs.start_domain, domain)
        self.assertEqual(bot_kwargs.username, "test")
        self.assertEqual(bot_kwargs._bot_id, "test")
        self.assertEqual(bot_kwargs.password, "pass")
        self.assertFalse(bot_kwargs.on_server)
        self.assertFalse(bot_kwargs.is_prompter)
        self.assertTrue(bot_kwargs.enable_responses)
        from chatbot_core.utils.enum import BotTypes
        self.assertEqual(bot_kwargs.bot_type, BotTypes.SUBMIND)
        self.assertTrue(bot_kwargs.shout_thread.is_alive())

        bot_kwargs.exit()
        self.assertEqual(bot_kwargs.shout_queue.qsize(), 0)
        clean_up.assert_called_once_with(bot_kwargs)

        bot_args = ChatBot(self.socket, domain, "test", "")
        self.assertIsInstance(bot_args, ChatBotABC)
        self.assertEqual(bot_args.socket, self.socket)
        self.assertEqual(bot_args.start_domain, domain)
        self.assertEqual(bot_args.username, "test")
        self.assertEqual(bot_args._bot_id, "test")
        self.assertIsNone(bot_args.password)
        self.assertTrue(bot_args.on_server)
        self.assertFalse(bot_args.is_prompter)
        self.assertTrue(bot_args.enable_responses)
        from chatbot_core.utils.enum import BotTypes
        self.assertEqual(bot_args.bot_type, BotTypes.SUBMIND)
        self.assertTrue(bot_args.shout_thread.is_alive())

        bot_args.exit()
        self.assertEqual(bot_args.shout_queue.qsize(), 0)
        clean_up.assert_called_with(bot_args)

    # TODO


class ChatBotV2Tests(unittest.TestCase):
    @patch("chatbot_core.v2.KlatAPIMQ", new=MockMQ)
    def test_init(self):
        from chatbot_core.v2 import ChatBot
        config = {"test": True,
                  "MQ": {"mq_key": "val"},
                  "chatbots": {"test_bot": {"bot_config": True}}}
        from chatbot_core.utils.enum import BotTypes
        bot_kwargs = ChatBot(config=config, service_name="test_bot",
                             vhost="/test", bot_type=BotTypes.OBSERVER)
        self.assertEqual(bot_kwargs.bot_type, BotTypes.OBSERVER)
        self.assertEqual(bot_kwargs._bot_id, "test_bot")
        self.assertEqual(bot_kwargs.config, config["MQ"])
        self.assertEqual(bot_kwargs.bot_config, config["chatbots"]["test_bot"])
        self.assertEqual(bot_kwargs.vhost, "/test")
        self.assertTrue(bot_kwargs.shout_thread.is_alive())
        bot_kwargs.shutdown()
        self.assertFalse(bot_kwargs.shout_thread.is_alive())

        bot_args = ChatBot(config, "args_bot", "/chat")
        self.assertEqual(bot_args.bot_type, BotTypes.SUBMIND)
        self.assertEqual(bot_args._bot_id, "args_bot")
        self.assertEqual(bot_args.config, config["MQ"])
        self.assertEqual(bot_args.bot_config, dict())
        self.assertEqual(bot_args.vhost, "/chat")
        self.assertTrue(bot_args.shout_thread.is_alive())
        bot_args.shutdown()
        self.assertFalse(bot_args.shout_thread.is_alive())
    # TODO


class ChatBotABCTests(unittest.TestCase):
    def test_base_class(self):
        from queue import Queue
        from chatbot_core.chatbot_abc import ChatBotABC
        from .mocks import TestBot
        bot_id = "test"
        test_config = {"config": True}
        bot = TestBot(bot_id, test_config)
        self.assertIsInstance(bot, ChatBotABC)
        self.assertEqual(bot._bot_id, bot_id)
        self.assertEqual(bot.bot_config, test_config)
        self.assertIsInstance(bot.shout_queue, Queue)
        self.assertIsInstance(bot.log, Logger)
        self.assertTrue(bot.log.name.startswith(bot_id))


class NeonTests(unittest.TestCase):
    from chatbot_core.neon import NeonBot
    # TODO Implement tests or deprecate base class


class ParlaiTests(unittest.TestCase):
    from chatbot_core.parlai import ParlaiBot
    # TODO Implement tests or deprecate base class


if __name__ == '__main__':
    unittest.main()

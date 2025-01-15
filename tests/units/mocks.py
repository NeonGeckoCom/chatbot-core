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
from typing import Optional
from unittest.mock import MagicMock
from chatbot_core.chatbot_abc import ChatBotABC


class MockMQ(MagicMock):
    def __init__(self, config, service_name, vhost):
        self.service_name = service_name
        self.config = config
        self.vhost = vhost
        self.current_conversations = set()
        self.is_running = True
        self._service_id = "test_id"

        self.vhost_prefix = None
        self.testing_envs = set()


class TestBot(ChatBotABC):
    def on_vote(self, prompt_id: str, selected: str, voter: str):
        pass

    def on_discussion(self, user: str, shout: str):
        pass

    def on_proposed_response(self):
        pass

    def on_selection(self, prompt: str, user: str, response: str):
        pass

    def on_ready_for_next(self, user: str):
        pass

    def at_chatbot(self, user: str, shout: str, timestamp: str) -> str:
        pass

    def ask_proctor(self, prompt: str, user: str, cid: str, dom: str):
        pass

    def ask_chatbot(self, user: str, shout: str, timestamp: str) -> str:
        pass

    def ask_history(self, user: str, shout: str, dom: str, cid: str) -> str:
        pass

    def ask_appraiser(self, options: dict) -> str:
        pass

    def ask_discusser(self, options: dict) -> str:
        pass

    def _send_first_prompt(self):
        pass

    def handle_shout(self, *args, **kwargs):
        pass

    def vote_response(self, response_user: str, cid: Optional[str] = None):
        pass

    def _handle_next_shout(self):
        pass

    def _pause_responses(self, duration: int = 5):
        pass

    def parse_init(self, *args, **kwargs) -> tuple:
        pass

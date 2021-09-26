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
import time

from neon_utils.socket_utils import b64_to_dict, dict_to_b64
from neon_utils import LOG

from klat_connector.mq_klat_api import KlatAPIMQ
from chatbot_core.chatbot_abc import ChatBotABC
from chatbot_core.utils import BotTypes


class ChatBot(KlatAPIMQ, ChatBotABC):
    """MQ-based chatbot implementation"""

    def __init__(self, config: dict, service_name: str, vhost: str, bot_type: str = BotTypes.SUBMIND):
        super().__init__(config, service_name, vhost)
        self.bot_type = bot_type

    def handle_kick_out(self, channel, method, _, body):
        """Handles incoming request to chat bot"""
        body_data = b64_to_dict(body)
        self.current_conversations.remove(body_data.get('cid', None))

    def handle_invite(self, channel, method, _, body):
        """Handles incoming request to chat bot"""
        body_data = b64_to_dict(body)
        if body_data.get('cid', None):
            self.current_conversations.add(body_data['cid'])

    def _setup_listeners(self):
        super()._setup_listeners()
        self.register_consumer('invitation',
                               self.vhost,
                               f'{self.nick}_invite',
                               self.handle_invite,
                               self.default_error_handler)
        self.register_consumer('kick_out',
                               self.vhost,
                               f'{self.nick}_kick_out',
                               self.handle_kick_out,
                               self.default_error_handler)
        self.register_consumer('user_message',
                               self.vhost,
                               f'{self.nick}_user_message',
                               self._on_mentioned_user_message,
                               self.default_error_handler)

    def _on_mentioned_user_message(self, channel, method, _, body):
        body_data = b64_to_dict(body)
        if body_data.get('cid', None) in self.current_conversations:
            self.handle_incoming_shout(body_data)
        else:
            LOG.warning(f'Skipping processing of mentioned user message with data: {body_data}')

    def handle_incoming_shout(self, message_data: dict):
        shout = message_data.get('shout', None)
        if shout:
            response = self.ask_chatbot(user=message_data.get('user', 'anonymous'),
                                        shout=shout,
                                        timestamp=str(message_data.get('timestamp', int(time.time()))))
            if response:
                self._send_shout('bot_response', {
                    'nick': self.nick,
                    'bot_type': self.bot_type,
                    'service_name': self.service_name,
                    'cid': message_data.get('cid', None),
                    'time': str(int(time.time())),
                    'shout': response
                })
            else:
                LOG.warning(f'{self.nick}: No response was sent as no data was received from message data: {message_data}')
        else:
            LOG.warning(f'{self.nick}: Missing "shout" in received message data: {message_data}')

    def _on_connect(self):
        self._send_shout('connection', {'nick': self.nick,
                                        'bot_type': self.bot_type,
                                        'service_name': self.service_name,
                                        'time': time.time()})
        self.is_running = True

    def _on_disconnect(self):
        self._send_shout('disconnection', {'nick': self.nick,
                                           'bot_type': self.bot_type,
                                           'service_name': self.service_name,
                                           'time': time.time()})
        self.is_running = False

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

    @staticmethod
    def _shout_is_prompt(shout):
        pass

    def _send_first_prompt(self):
        pass

    def _handle_next_shout(self):
        pass

    def _pause_responses(self, duration: int = 5):
        pass

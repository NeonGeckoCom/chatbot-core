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

from abc import abstractmethod

from neon_utils.socket_utils import b64_to_dict, dict_to_b64
from neon_utils import LOG

from klat_connector.mq_klat_api import KlatAPIMQ
from chatbot_core.chatbot_abc import ChatBotABC
from chatbot_core.utils import BotTypes


class ChatBot(KlatAPIMQ, ChatBotABC):
    """MQ-based chatbot implementation"""

    def __init__(self, *args, **kwargs):
        config, service_name, vhost, bot_type = self.parse_init(*args, **kwargs)
        super().__init__(config, service_name, vhost)
        self.bot_type = bot_type
        self.current_conversations = dict()
        self.on_server = False
        self.init_greetings()
        self.init_small_talk()

    def parse_init(self, *args, **kwargs) -> tuple:
        """Parses dynamic params input to ChatBot v2"""
        config, service_name, vhost, bot_type = (list(args) + [None] * 4)[:4]
        config: dict = config or kwargs.get('config', {})
        service_name: str = service_name or kwargs.get('service_name', 'undefined_service')
        vhost: str = vhost or kwargs.get('vhost', '/')
        bot_type: repr(BotTypes) = bot_type or kwargs.get('bot_type', BotTypes.SUBMIND)
        return config, service_name, vhost, bot_type

    def handle_kick_out(self, channel, method, _, body):
        """Handles incoming request to chat bot"""
        body_data = b64_to_dict(body)
        cid = body_data.get('cid', None)
        LOG.info(f'Received kick out from cid: {cid}')
        if cid:
            self.current_conversations.pop(cid, None)

    def handle_invite(self, channel, method, _, body):
        """Handles incoming request to chat bot"""
        body_data = b64_to_dict(body)
        new_cid = body_data.pop('cid', None)
        LOG.info(f'Received invitation to cid: {new_cid}')
        if new_cid and not self.current_conversations.get(new_cid, None):
            self.current_conversations[new_cid] = body_data

    def _setup_listeners(self):
        super()._setup_listeners()
        LOG.info(f'Registering handlers: {[self.nick+"_invite", self.nick+"_kick_out", self.nick+"_user_message"]}')
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
        """
            MQ handler for mentioned user message
        """
        body_data = b64_to_dict(body)
        if body_data.get('cid', None) in list(self.current_conversations):
            self.handle_incoming_shout(body_data)
        else:
            LOG.warning(f'Skipping processing of mentioned user message with data: {body_data}')

    def handle_incoming_shout(self, message_data: dict):
        """
            Handles incoming shout for bot. If receives response - emits message into "bot_response" queue

            :param message_data: dict containing message data received
        """
        LOG.info(f'Message data: {message_data}')
        shout = message_data.get('shout', None) or message_data.get('messageText', None)
        if shout:
            LOG.info(f'Received incoming shout: {shout}')
            response = self.ask_chatbot(user=message_data.get('user', 'anonymous'),
                                        shout=shout,
                                        timestamp=str(message_data.get('timeCreated', int(time.time()))))
            if response:
                LOG.info(f'Sending response: {response}')

                self._send_shout('bot_response', {
                    'nick': self.nick,
                    'bot_type': self.bot_type,
                    'service_name': self.service_name,
                    'cid': message_data.get('cid', ''),
                    'responded_shout': message_data.get('messageID', ''),
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

    def _on_disconnect(self):
        self._send_shout('disconnection', {'nick': self.nick,
                                           'bot_type': self.bot_type,
                                           'service_name': self.service_name,
                                           'time': time.time()})

    def sync(self, vhost: str = None, exchange: str = None, queue: str = None, request_data: dict = None):
        """
            Periodical notification message to be sent into MQ,
            used to notify other network listeners about this service health status

            :param vhost: mq virtual host (defaults to self.vhost)
            :param exchange: mq exchange (defaults to base one)
            :param queue: message queue prefix (defaults to self.service_name)
            :param request_data: data to publish in sync
        """
        curr_time = int(time.time())
        LOG.info(f'{curr_time} Emitting sync message from {self.nick}')
        self._on_connect()

    def handle_shout(self, user: str, shout: str, cid: str, dom: str, timestamp: str):
        pass

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

    def pre_run(self, **kwargs):
        self._setup_listeners()

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

from queue import Queue
from threading import Thread
from typing import Tuple

from neon_utils.socket_utils import b64_to_dict
from neon_utils import LOG

from klat_connector.mq_klat_api import KlatAPIMQ

from chatbot_core import ConversationState
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
        self.shout_queue = Queue(maxsize=256)
        self.shout_thread = Thread(target=self._handle_next_shout, daemon=True)
        self.shout_thread.start()

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
            self.set_conversation_state(new_cid, ConversationState.IDLE)
            # TODO: emit greeting here (Kirill)

    def get_conversation_state(self, cid) -> ConversationState:
        return self.current_conversations.get(cid, {}).get('state', ConversationState.IDLE)

    def set_conversation_state(self, cid, state):
        self.current_conversations.setdefault(cid, {})['state'] = state

    def _setup_listeners(self):
        super()._setup_listeners()
        LOG.info(
            f'Registering handlers: {[self.nick + "_invite", self.nick + "_kick_out", self.nick + "_user_message"]}')
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
            LOG.warning(f'Skipping processing of mentioned user message with data: {body_data} '
                        f'as it is not in current conversations')

    def _on_user_message(self, channel, method, _, body):
        """
            MQ handler for mentioned user message
        """
        body_data = b64_to_dict(body)
        # Processing message in case its either broadcast or its received is this instance,
        # forbids recursive calls
        if body_data.get('broadcast', False) or \
                body_data.get('receiver', None) == self.nick and \
                self.nick != body_data.get('user', None):
            self._on_mentioned_user_message(channel, method, _, body)

    def handle_incoming_shout(self, message_data: dict):
        """
            Handles an incoming shout into the current conversation
            :param message_data: data of incoming message
        """
        self.shout_queue.put(message_data)

    def make_response(self, cid, message_data, shout, message_sender, is_message_from_proctor,
                      conversation_state) -> Tuple[str, str]:
        """
            Makes response based on incoming message data and its context
            :param cid: current conversation id
            :param message_data: message data received
            :param shout: incoming shout data
            :param message_sender: nick of message sender
            :param is_message_from_proctor: is message sender a Proctor
            :param conversation_state: state of the conversation from ConversationStates

            :returns response and response queue to which publish response
        """
        response = None
        LOG.info(f'Received incoming shout: {shout}')
        response_queue = None
        if not is_message_from_proctor:
            response = self.ask_chatbot(user=message_sender,
                                        shout=shout,
                                        timestamp=str(message_data.get('timeCreated', int(time.time()))))
        else:
            response_queue = f'{message_sender}_user_message'
            self.set_conversation_state(cid, conversation_state)
            if conversation_state in (ConversationState.IDLE, ConversationState.RESP,):
                response = self.ask_chatbot(user=message_sender,
                                            shout=shout,
                                            timestamp=str(message_data.get('timeCreated', int(time.time()))))
            elif conversation_state == ConversationState.DISC:
                start_time = time.time()
                options: dict = message_data.get('proposed_responses', {})
                response = self.ask_discusser(options)
                if response:
                    self._hesitate_before_response(start_time=start_time)
                    self.discuss_response(response)
            elif conversation_state == ConversationState.VOTE:
                start_time = time.time()
                selected = self.ask_appraiser(options=message_data.get('proposed_responses', {}))
                self._hesitate_before_response(start_time)
                if not selected or selected == self.nick:
                    selected = "abstain"
                response = self.vote_response(selected)
            elif conversation_state == ConversationState.WAIT:
                response = 'I am ready for the next prompt'
        return response, response_queue

    def handle_shout(self, message_data: dict):
        """
            Handles shout for bot. If receives response - emits message into "bot_response" queue

            :param message_data: dict containing message data received
        """
        LOG.info(f'Message data: {message_data}')
        shout = message_data.get('shout') or message_data.get('messageText', '')
        cid = message_data.get('cid', '')
        conversation_state = ConversationState(message_data.get('conversation_state', 0)).name
        message_sender = message_data.get('user', 'anonymous')
        is_message_from_proctor = self._user_is_proctor(message_sender)
        default_queue_name = 'user_message'
        if shout:
            response, queue_name = self.make_response(cid=cid, message_data=message_data,
                                                      shout=shout, message_sender=message_sender,
                                                      is_message_from_proctor=is_message_from_proctor,
                                                      conversation_state=conversation_state)
            if response:
                LOG.info(f'Sending response: {response}')
                self.send_shout(response,
                                responded_message=message_data.get('messageID', ''),
                                cid=cid,
                                dom=message_data.get('dom', ''),
                                queue_name=queue_name or default_queue_name)
            else:
                LOG.warning(
                    f'{self.nick}: No response was sent as no data was received from message data: {message_data}')
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

    def discuss_response(self, shout: str, cid: str = None):
        """
        Called when a bot has some discussion to share
        :param shout: Response to post to conversation
        :param cid: mentioned conversation id
        """
        if self.get_conversation_state(cid) != ConversationState.DISC:
            LOG.warning(f"Late Discussion! {shout}")
        elif not shout:
            LOG.warning(f"Empty discussion provided! ({self.nick})")
        else:
            LOG.info('Shout response is valid')

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

    def send_shout(self, shout, responded_message=None, cid: str = None, dom: str = None, queue_name='bot_response'):
        """
            Convenience method to emit shout via MQ with extensive instance properties

            :param shout: response message to emit
            :param responded_message: responded message if any
            :param cid: id of desired conversation
            :param dom: domain name
            :param queue_name: name of the response mq queue
        """
        if not cid:
            LOG.warning('No cid was mentioned')
            return
        conversation_state = self.get_conversation_state(cid)
        self._send_shout(queue_name, {
            'nick': self.nick,
            'bot_type': self.bot_type,
            'service_name': self.service_name,
            'cid': cid,
            'dom': dom,
            'conversation_state': conversation_state,
            'responded_shout': responded_message,
            'shout': shout,
            'time': str(int(time.time()))})

    def vote_response(self, response_user: str, cid: str = None):
        """
            For V2 it is possible to participate in discussions for multiple conversations
            but no more than one discussion per conversation.
        """
        if cid and self.get_conversation_state(cid) != ConversationState.VOTE:
            LOG.warning(f"Late Vote! {response_user}")
            return None
        elif not response_user:
            LOG.error("Null response user returned!")
            return None
        elif response_user == "abstain" or response_user == self.nick:
            # self.log.debug(f"Abstaining voter! ({self.nick})")
            return "abstain"
        else:
            self.send_shout(f"I vote for {response_user}")
            return response_user

    def _handle_next_shout(self):
        """
            Called recursively to handle incoming shouts synchronously
        """
        curr_time = int(time.time())
        # checks for processing the new series of shouts each 10 seconds
        while int(time.time()) - curr_time > 10:
            next_message_data = self.shout_queue.get()
            while next_message_data:
                self.handle_shout(next_message_data)
                next_message_data = self.shout_queue.get()

    def _pause_responses(self, duration: int = 5):
        pass

    def pre_run(self, **kwargs):
        self._setup_listeners()

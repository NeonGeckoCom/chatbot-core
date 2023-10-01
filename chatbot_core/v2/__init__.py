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
import time

from neon_mq_connector.utils import RepeatingTimer
from neon_mq_connector.utils.rabbit_utils import create_mq_callback

from klat_connector.mq_klat_api import KlatAPIMQ
from pika.exchange_type import ExchangeType

from chatbot_core import ConversationState
from chatbot_core.chatbot_abc import ChatBotABC
from chatbot_core.utils import BotTypes


class ChatBot(KlatAPIMQ, ChatBotABC):
    """MQ-based chatbot implementation"""

    def __init__(self, *args, **kwargs):
        config, service_name, vhost, bot_type = self.parse_init(*args, **kwargs)
        KlatAPIMQ.__init__(self, config, service_name, vhost)
        ChatBotABC.__init__(self)
        self.bot_type = bot_type
        self.current_conversations = dict()
        self.on_server = True
        self.default_response_queue = 'shout'
        self.shout_thread = RepeatingTimer(function=self._handle_next_shout,
                                           interval=kwargs.get('shout_thread_interval', 10))
        self.shout_thread.start()

    def parse_init(self, *args, **kwargs) -> tuple:
        """Parses dynamic params input to ChatBot v2"""
        config, service_name, vhost, bot_type = (list(args) + [None] * 4)[:4]
        config: dict = config or kwargs.get('config', {})
        service_name: str = service_name or kwargs.get('service_name', 'undefined_service')
        vhost: str = vhost or kwargs.get('vhost', '/')
        bot_type: repr(BotTypes) = bot_type or kwargs.get('bot_type', BotTypes.SUBMIND)
        return config, service_name, vhost, bot_type

    @create_mq_callback()
    def handle_kick_out(self, body: dict):
        """Handles incoming request to chatbot"""
        cid = body.get('cid', None)
        self.log.info(f'Received kick out from cid: {cid}')
        if cid:
            self.send_announcement(f'{self.nick.split("-")[0]} kicked out', cid)
            self.current_conversations.pop(cid, None)

    @create_mq_callback()
    def handle_invite(self, body: dict):
        """Handles incoming request to chatbot"""
        new_cid = body.pop('cid', None)
        self.log.info(f'Received invitation to cid: {new_cid}')
        if new_cid and not self.current_conversations.get(new_cid, None):
            self.current_conversations[new_cid] = body
            self.set_conversation_state(new_cid, ConversationState.IDLE)
            self.send_announcement(f'{self.nick.split("-")[0]} joined', new_cid)

    def get_conversation_state(self, cid) -> ConversationState:
        return self.current_conversations.get(cid, {}).get('state', ConversationState.IDLE)

    def set_conversation_state(self, cid, state):
        self.log.debug(f'State was: {self.current_conversations.setdefault(cid, {}).get("state", ConversationState.IDLE)}')
        self.current_conversations.setdefault(cid, {})['state'] = state
        self.log.debug(
            f'State become: {self.current_conversations.setdefault(cid, {}).get("state", ConversationState.IDLE)}')

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
        self.register_consumer('incoming_shout',
                               self.vhost,
                               f'{self.nick}_shout',
                               self._on_mentioned_user_message,
                               self.default_error_handler)
        self.register_subscriber('proctor_message',
                                 self.vhost,
                                 self._on_mentioned_user_message,
                                 self.default_error_handler,
                                 exchange='proctor_shout')
        self.register_subscriber('proctor_ping',
                                 self.vhost,
                                 self.handle_proctor_ping,
                                 self.default_error_handler,
                                 exchange='proctor_ping')

    @create_mq_callback()
    def handle_proctor_ping(self, body: dict):
        if body.get('cid') in list(self.current_conversations):
            with self.create_mq_connection(self.vhost) as mq_connection:
                proctor_nick = body.get('nick', '')
                self.log.info(f'Sending pong to {proctor_nick}')
                self.publish_message(mq_connection, request_data=dict(nick=self.nick,
                                                                      cid=body.get('cid')),
                                     exchange=f'{proctor_nick}_pong',
                                     expiration=3000)
                self.set_conversation_state(body.get('cid'), ConversationState.WAIT)
                self.send_shout(shout='I am ready for the next prompt',
                                cid=body.get('cid'))

    @create_mq_callback()
    def _on_mentioned_user_message(self, body: dict):
        """
            MQ handler for requesting message for current bot
        """
        if body.get('cid', None) in list(self.current_conversations) and not body.get('omit_reply', False):
            self.handle_incoming_shout(body)
        else:
            self.log.warning(f'Skipping processing of mentioned user message with data: {body} '
                        f'as it is not in current conversations')

    @create_mq_callback()
    def _on_user_message(self, body: dict):
        """
            MQ handler for requesting message, gets processed in case its addressed to given instance or is a broadcast call
        """
        # Processing message in case its either broadcast or its received is this instance,
        # forbids recursive calls
        if body.get('broadcast', False) or \
                body.get('receiver', None) == self.nick and \
                self.nick != body.get('user', None):
            self._on_mentioned_user_message('', '', '', body)

    def handle_incoming_shout(self, message_data: dict):
        """
            Handles an incoming shout into the current conversation
            :param message_data: data of incoming message
        """
        self.shout_queue.put(message_data)

    @property
    def contextual_api_supported(self) -> bool:
        """ This is a backward compatibility property to ensure gradual migration of V2 subminds API to enable handling of the context """
        # TODO: make it defaulting to True once all the related subminds are migrated (Kirill)
        return False

    def get_chatbot_response(self, cid, message_data, shout, message_sender, is_message_from_proctor,
                             conversation_state) -> dict:
        """
            Makes response based on incoming message data and its context
            :param cid: current conversation id
            :param message_data: message data received
            :param shout: incoming shout data
            :param message_sender: nick of message sender
            :param is_message_from_proctor: is message sender a Proctor
            :param conversation_state: state of the conversation from ConversationStates

            :returns response data as a dictionary, example:
                {
                 "shout": "I vote for Wolfram",
                 "context": {"selected": "wolfram"},
                 "queue": "pat_user_message"
                }
        """
        response = {'shout': '', 'context': {}, 'queue': ''}
        self.log.info(f'Received incoming shout: {shout}')
        if self.contextual_api_supported:
            context_kwargs = {'context': self._build_submind_request_context(message_data=message_data,
                                                                             message_sender=message_sender,
                                                                             is_message_from_proctor=is_message_from_proctor,
                                                                             conversation_state=conversation_state)}
        else:
            context_kwargs = {}
        if not is_message_from_proctor:
            response['shout'] = self.ask_chatbot(user=message_sender,
                                                 shout=shout,
                                                 timestamp=str(message_data.get('timeCreated', int(time.time()))),
                                                 **context_kwargs)
        else:
            response['to_discussion'] = '1'
            response['conversation_state'] = conversation_state
            message_sender = BotTypes.PROCTOR

            self.set_conversation_state(cid, conversation_state)
            if conversation_state == ConversationState.RESP:
                response['shout'] = self.ask_chatbot(user=message_sender,
                                                     shout=shout,
                                                     timestamp=str(message_data.get('timeCreated', int(time.time()))),
                                                     **context_kwargs)
            elif conversation_state == ConversationState.DISC:
                options: dict = message_data.get('proposed_responses', {})
                response['shout'] = self.ask_discusser(options, **context_kwargs)
            elif conversation_state == ConversationState.VOTE:
                selected = self.ask_appraiser(options=message_data.get('proposed_responses', {}), **context_kwargs)
                response['shout'] = self.vote_response(selected)
                if 'abstain' in response['shout'].lower():
                    selected = "abstain"
                response['context']['selected'] = selected
            elif conversation_state == ConversationState.WAIT:
                response['shout'] = 'I am ready for the next prompt'
            response['context']['prompt_id'] = message_data.get('prompt_id', '')
        return response

    @staticmethod
    def _build_submind_request_context(message_data: dict,
                                       message_sender: str,
                                       is_message_from_proctor: bool,
                                       conversation_state: ConversationState) -> dict:
        return {
            'prompt_id': message_data.get('prompt_id', ''),
            'message_sender': message_sender,
            'is_message_from_proctor': is_message_from_proctor,
            'conversation_state': conversation_state,
        }

    def handle_shout(self, message_data: dict, skip_callback: bool = False):
        """
            Handles shout for bot. If receives response - emits message into "bot_response" queue

            :param message_data: dict containing message data received
            :param skip_callback: to skip callback after handling shoult (default to False)
        """
        self.log.info(f'Message data: {message_data}')
        shout = message_data.get('shout') or message_data.get('messageText', '')
        cid = message_data.get('cid', '')
        conversation_state = ConversationState(message_data.get('conversation_state', 0))
        message_sender = message_data.get('nick', 'anonymous')
        is_message_from_proctor = self._user_is_proctor(message_sender)
        if shout:
            response = self.get_chatbot_response(cid=cid, message_data=message_data,
                                                 shout=shout, message_sender=message_sender,
                                                 is_message_from_proctor=is_message_from_proctor,
                                                 conversation_state=conversation_state)
            shout = response.get('shout', None)
            if shout and not skip_callback:
                self.log.info(f'Sending response: {response}')
                prompt_id = response.get('context', {}).get('prompt_id')
                self.send_shout(shout=shout,
                                responded_message=message_data.get('messageID', ''),
                                cid=cid,
                                to_discussion=response.get('to_discussion', '0'),
                                queue_name=response.get('queue', None),
                                context=response.get('context', None),
                                is_announcement=response.get('is_announcement', False),
                                prompt_id=prompt_id,
                                **response.get('kwargs', {}))
            else:
                self.log.warning(
                    f'{self.nick}: No response was sent as no data was received from message data: {message_data}')
        else:
            self.log.warning(f'{self.nick}: Missing "shout" in received message data: {message_data}')

    def _on_connect(self):
        """Emits fanout message to connection exchange once connecting"""
        self.send_shout(shout='hello',
                        context={'version': os.environ.get('SERVICE_VERSION', 'undefined'),
                                 'bot_type': self.bot_type},
                        exchange='connection')

    def _on_disconnect(self):
        """Emits fanout message to connection exchange once disconnecting"""
        self.send_shout(shout='bye',
                        exchange='disconnection')

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
        self.log.info(f'{curr_time} Emitting sync message from {self.nick}')
        self._on_connect()

    def discuss_response(self, shout: str, cid: str = None):
        """
        Called when a bot has some discussion to share
        :param shout: Response to post to conversation
        :param cid: mentioned conversation id
        """
        if self.get_conversation_state(cid) != ConversationState.DISC:
            self.log.warning(f"Late Discussion! {shout}")
        elif not shout:
            self.log.warning(f"Empty discussion provided! ({self.nick})")

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

    def ask_chatbot(self, user: str, shout: str, timestamp: str, context: dict = None) -> str:
        pass

    def ask_history(self, user: str, shout: str, dom: str, cid: str) -> str:
        pass

    def ask_appraiser(self, options: dict, context: dict = None) -> str:
        pass

    def ask_discusser(self, options: dict, context: dict = None) -> str:
        pass

    def _send_first_prompt(self):
        pass

    def send_shout(self, shout, responded_message=None, cid: str = '', dom: str = '',
                   queue_name='',
                   exchange='',
                   broadcast: bool = True,
                   context: dict = None,
                   prompt_id='',
                   **kwargs) -> str:
        """
            Convenience method to emit shout via MQ with extensive instance properties

            :param shout: response message to emit
            :param responded_message: responded message if any
            :param cid: id of desired conversation
            :param dom: domain name
            :param queue_name: name of the response mq queue
            :param exchange: name of mq exchange
            :param broadcast: to broadcast shout (defaults to True)
            :param context: message context to pass along with response
            :param prompt_id: id of prompt to refer shout to

            :returns generated shout id
        """
        conversation_state = self.get_conversation_state(cid)
        if isinstance(conversation_state, ConversationState):
            conversation_state = conversation_state.value
        queue_name = queue_name or self.default_response_queue
        if broadcast:
            # prohibits fanouts to default exchange for consistency
            exchange = exchange or queue_name
            queue_name = ''
            exchange_type = ExchangeType.fanout.value
        else:
            exchange_type = ExchangeType.direct.value

        kwargs.setdefault('omit_reply', False)
        kwargs.setdefault('no_save', False)

        return self._send_shout(
            queue_name=queue_name,
            exchange=exchange,
            exchange_type=exchange_type,
            message_body={
                'nick': self.nick,
                'bot_type': self.bot_type,
                'service_name': self.service_name,
                'cid': cid,
                'dom': dom,
                'conversation_state': conversation_state,
                'responded_shout': responded_message,
                'shout': shout,
                'context': context or {},
                'prompt_id': prompt_id,
                'time': str(int(time.time())),
                **kwargs})

    def send_announcement(self, shout, cid, **kwargs):
        return self.send_shout(shout=shout,
                               cid=cid,
                               is_announcement='1',
                               **kwargs)

    def vote_response(self, response_user: str, cid: str = None):
        """
            For V2 it is possible to participate in discussions for multiple conversations
            but no more than one discussion per conversation.
        """
        if cid and self.get_conversation_state(cid) != ConversationState.VOTE:
            self.log.warning(f"Late Vote! {response_user}")
            return ''
        elif not response_user:
            self.log.error("Null response user returned!")
            return ''
        elif response_user == "abstain" or response_user in (self.nick, self.service_name):
            # self.self.log.debug(f"Abstaining voter! ({self.nick})")
            return "I abstain from voting"
        else:
            return f"I vote for {response_user}"

    def _handle_next_shout(self):
        """
            Called recursively to handle incoming shouts synchronously
        """
        next_message_data = self.shout_queue.get()
        while next_message_data:
            self.handle_shout(next_message_data)
            next_message_data = self.shout_queue.get()

    def _pause_responses(self, duration: int = 5):
        pass

    def pre_run(self, **kwargs):
        self._setup_listeners()

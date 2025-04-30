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
import time
from typing import Dict

from neon_mq_connector.utils import RepeatingTimer
from neon_mq_connector.utils.rabbit_utils import create_mq_callback
from klat_connector.mq_klat_api import KlatAPIMQ
from pika.exchange_type import ExchangeType
from neon_data_models.models.api.mq.chatbots import ChatbotsMqRequest, \
    ChatbotsMqSubmindResponse
from neon_data_models.enum import CcaiState as ConversationState

from chatbot_core.utils.enum import BotTypes
from chatbot_core.chatbot_abc import ChatBotABC
from chatbot_core.version import __version__ as package_version


class ChatBot(KlatAPIMQ, ChatBotABC):
    """MQ-based chatbot implementation"""

    async_consumers_enabled = True

    def __init__(self, *args, **kwargs):
        config, service_name, vhost, bot_type = self.parse_init(*args, **kwargs)
        mq_config = config.get("MQ") or config
        bot_config = config.get("chatbots", {}).get(service_name)
        KlatAPIMQ.__init__(self, mq_config, service_name, vhost)
        ChatBotABC.__init__(self, service_name, bot_config)
        self.bot_type = bot_type

        # Mapping of CID to context including `state` and `prompts`
        self.current_conversations: Dict[str, dict] = dict()
        # Mapping of prompt_id to associated CID
        self.prompt_to_cid: Dict[str, str] = dict()
        self.on_server = True
        self.supports_raw_conversation = True
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
        bot_type: BotTypes = bot_type or kwargs.get('bot_type', BotTypes.SUBMIND)
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
        announce_invitation = body.pop('announce_invitation', True)
        self.log.info(f'Received invitation to cid: {new_cid}')
        if new_cid and not self.current_conversations.get(new_cid, None):
            self.current_conversations[new_cid] = body
            self.set_conversation_state(new_cid, ConversationState.IDLE)
            if announce_invitation:
                self.send_announcement(f'{self.nick.split("-")[0]} joined',
                                       new_cid)

    def get_conversation_state(self, cid: str) -> ConversationState:
        """
        Get the state of a conversation
        """
        return self.current_conversations.get(cid,
                                              {}).get('state', 
                                                      ConversationState.IDLE)

    def set_conversation_state(self, cid: str, state: ConversationState):
        """
        Set/update the state of a conversation
        """
        old_state = self.current_conversations.setdefault(cid, {}).get(
            "state", ConversationState.IDLE)
        self.log.debug(f'State was: {old_state}')
        self.current_conversations.setdefault(cid, {})['state'] = state
        new_state = self.current_conversations.setdefault(cid, {}).get(
            "state", ConversationState.IDLE)
        self.log.debug(f'State became: {new_state}')

    def _setup_listeners(self):
        KlatAPIMQ._setup_listeners(self)
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
                self.log.debug(f'Sending pong to {proctor_nick}')
                self.publish_message(mq_connection,
                                     request_data=dict(nick=self.nick,
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
        # TODO: Backwards-compat. data key handling
        if "shout" in body:
            body.setdefault("message_text", body.get('shout', ''))

        message = ChatbotsMqRequest(**body)
        if body.get('omit_reply'):
            self.log.debug(f"Explicitly requested no response: messageID="
                           f"{body.get('messageID')}")
            return
        if message.cid not in list(self.current_conversations):
            self.log.debug(f"Ignoring message "
                          f"(messageID={body.get('messageID')}) outside of "
                          f"current conversations "
                          f"({self.current_conversations})")
            self.log.debug(f"{body}")
            return
        # `routing_key` check is a hack to exclude old messages from Proctor
        if self.supports_raw_conversation and "routing_key" not in body and \
                self._user_is_proctor(message.username):
            self.log.debug(f"Ignoring proctor message: {body=}")
            return
        self.handle_incoming_shout(message.model_dump())

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
        else:
            self.log.warning(f"Ignoring message: {body}")

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

    @staticmethod
    def _build_submind_request_context(message_data: dict,
                                       message_sender: str,
                                       is_message_from_proctor: bool,
                                       conversation_state: ConversationState) -> dict:
        return {
            'prompt_id': message_data.get('prompt_id', ''),
            'message_sender': message_sender,
            'is_message_from_proctor': is_message_from_proctor,
            'conversation_state': conversation_state.value,
        }

    def handle_shout(self, message_data: dict):
        """
            Handles shout for bot. If receives response - emits message into "bot_response" queue

            :param message_data: dict containing message data received
            :param skip_callback: to skip callback after handling shout (default to False)
        """
        self.log.debug(f'Message data: {message_data}')
        message = ChatbotsMqRequest(**message_data)

        # Remove suffix from username if it's really a `user_id`
        if '-' in message.username:
            message.username = message.username.rsplit('-', 1)[0]

        shout = message.message_text
        cid = message.cid
        prompt_id = message.prompt_id
        response = None

        if "are selected for current prompt" in shout:
            self.log.info(f"Proctor selected next subminds: {message}")
            message.prompt_state = ConversationState.IDLE

        # Initialize prompt data structure if it doesn't exist
        if prompt_id and prompt_id not in self.prompt_to_cid:
            # TODO: Participants were announced prior to this message
            self.current_conversations.setdefault(cid, {})
            self.current_conversations[cid].setdefault("prompts", {})
            self.current_conversations[cid].setdefault("prompt_history", [])
            if prompt_id not in self.current_conversations[cid]['prompts']:
                self.current_conversations[cid]['prompts'][prompt_id] = {
                    "bot_name": self.service_name,
                    "participating_subminds": self.current_conversations[cid].pop('next_subminds', []),
                    "cycles": [{
                        "proposed_responses": {},
                        "discussion": [{}],
                        "votes": {}
                    }]
                }
            self.current_conversations[cid]['prompt_history'].append(prompt_id)
            self.prompt_to_cid[prompt_id] = cid
            self.log.info(
                f"Starting new prompt: {prompt_id}: {message.message_text}")


        message_sender = message.username
        is_message_from_proctor = self._user_is_proctor(message_sender)

        # Handle control messages that indicate a change in conversation phase
        changed = False
        if is_message_from_proctor:
            # Proctor cotrol message
            # TODO: Better check here
            if "accepting responses" in shout.lower():
                changed = True
                self.set_conversation_state(cid, ConversationState.RESP)
            elif "discussing responses" in shout.lower():
                changed = True
                self.set_conversation_state(cid, ConversationState.DISC)
            elif "voting for candidate responses" in shout.lower():
                changed = True
                self.set_conversation_state(cid, ConversationState.VOTE)
            elif "selecting a winner among participants" in shout.lower():
                changed = True
                self.set_conversation_state(cid, ConversationState.PICK)
            if changed:
                self.log.debug(f"Conversation state set from proctor shout: "
                            f"{self.get_conversation_state(cid)}")
            if not changed and \
                    message.prompt_state not in (None, ConversationState.IDLE):
                old_state = self.get_conversation_state(cid)
                self.set_conversation_state(cid, message.prompt_state)
                self.log.debug(f"Conversation state from message data: "
                                 f"{self.get_conversation_state(cid)}")
                if self.get_conversation_state(cid) != old_state:
                    self.log.warning(f"Conversation state changed by Proctor "
                                    f"message to {message.prompt_state}")
                    changed = True
        if changed:
            self.log.info(f"State changed to: "
                          f"{self.get_conversation_state(cid).name}")
            return

        # Handle any other message not related to conversation state handling
        conversation_state = self.get_conversation_state(cid)
        if prompt_id:
            current_prompt = \
                self.current_conversations[cid]['prompts'][prompt_id]

        if not prompt_id:
            if is_message_from_proctor:
                # Proctor control message
                # TODO: Can we re-define the proctor to always specify a prompt_id?
                if "are selected for current prompt" in shout:
                    next_subminds = shout.split("are selected")[0].split(',')
                    next_subminds = [s.replace('and', '').strip() for s in next_subminds]
                    self.log.info(f"Proctor selected next subminds: {next_subminds}")
                    self.current_conversations.setdefault(cid, {})
                    self.current_conversations[cid]['next_subminds'] = next_subminds
                else:
                    self.log.warning(f"Not handling proctor message: {shout}")
                return
            # Non-proctored conversation activity
            self.log.info(f"Non-proctored input: {message}")
            response = self.ask_chatbot(
                user=message_sender, shout=shout,
                timestamp=str(round(message.time_created.timestamp)))
            response = ChatbotsMqSubmindResponse(
                user_id=self.uid,
                username=self.nick,
                message_text=response,
                replied_message=message.message_id,
                bot='1',
                prompt_id=prompt_id,
                source="chatbot",
                to_discussion=True,
                prompt_state=conversation_state,
            )
        elif not is_message_from_proctor:
            # Submind response in proctored conversation
            self.log.debug(f"Handling non-proctor CCAI message. "
                           f"state={conversation_state.name}")
            if conversation_state == ConversationState.RESP:
                self.on_proposed_response(prompt_id, shout, message_sender)
            elif conversation_state == ConversationState.DISC:
                self.on_discussion(message_sender, shout, prompt_id)
            elif conversation_state == ConversationState.VOTE:
                self.on_vote(prompt_id, shout, message_sender)
            return
        elif conversation_state == ConversationState.PICK:
            # Proctor made a selection
            try:
                preamble, choice = shout.split(":", 1)
                winner = preamble.split(" ")[-1]
                choice = choice.strip().strip('"')
                self.on_selection(prompt_id, winner, choice)
            except ValueError:
                self.log.warning(f"Failed to parse winner from: {shout}")
            self.set_conversation_state(cid, ConversationState.IDLE)
            return
        elif conversation_state == ConversationState.RESP:
            # Proposal phase
            self.current_conversations[cid]['prompts'][prompt_id]\
                    ["prompt"] = message.message_text
            response = self.ask_chatbot(user=message_sender,
                                        shout=shout,
                                        timestamp=str(message.time_created.timestamp()))
        elif conversation_state == ConversationState.DISC:
            # Discussion phase
            options: dict = current_prompt["cycles"][-1].get('proposed_responses', {})
            current_prompt["cycles"][-1]['proposed_responses'] = options
            response = self.ask_discusser(options)
        elif conversation_state == ConversationState.VOTE:
            # Voting phase
            options: dict = current_prompt["cycles"][-1].get('proposed_responses', {})
            selected = self.ask_appraiser(options=options)
            response = self.vote_response(selected)
            if 'abstain' in response.lower():
                selected = "abstain"

        if response:
            self.log.info(f"Responding to: {message.message_text}")
            response = ChatbotsMqSubmindResponse(
                cid=message.cid,
                user_id=self.uid,
                username=self.service_name,
                message_text=response,
                replied_message=message.message_id,
                bot='1',
                prompt_id=prompt_id,
                source="chatbot",
                to_discussion=True,
                prompt_state=conversation_state,
                omit_reply=False,
                no_save=False
            )
            self.send_shout(responded_message=response.replied_message,
                            **response.model_dump())
            self.log.debug(f"Sent response:{response}")
        else:
            self.log.warning(
                f'No response generated with state={conversation_state.name} '
                f'{message_data=}.')

    def _send_state(self):
        self.send_shout(shout='chatbot state',
                        context={
                            'service_name': self.service_name,
                            'version': os.environ.get('SERVICE_VERSION', 
                                                      package_version),
                            'bot_type': self.bot_type,
                            'supports_raw_conversation': self.supports_raw_conversation,
                            'cids': list(self.current_conversations),
                        },
                        exchange='connection')

    def _on_connect(self):
        """Emits fanout message to connection exchange once connecting"""
        self._send_state()
        self._connected = True

    def _on_disconnect(self):
        """Emits fanout message to connection exchange once disconnecting"""
        self.send_shout(shout='bye',
                        exchange='disconnection')
        self._connected = False

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
        self.log.debug(f'{curr_time} Emitting sync message from {self.nick}')
        self._send_state()

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

    def on_proposed_response(self, prompt_id: str, response: str, user: str):
        if prompt_id not in self.prompt_to_cid:
            self.log.warning(f"Unknown prompt id: {prompt_id}")
            return
        prompt_data = self.current_conversations[self.prompt_to_cid[prompt_id]]\
            .get('prompts', {}).get(prompt_id, {})
        if not prompt_data:
            self.log.error(f"prompt data unexpectedly None for id={prompt_id}")
            return
        if user not in prompt_data['participating_subminds']:
            self.log.warning(f"{user} is not participating in this prompt")
            return
        prompt_data["cycles"][-1]['proposed_responses'][user] = response
        self.log.debug(f"Received proposed response from {user}: {response}")

    def on_discussion(self, user: str, shout: str, prompt_id: str):
        if prompt_id not in self.prompt_to_cid:
            self.log.warning(f"Unknown prompt id: {prompt_id}")
            return
        prompt_data = self.current_conversations[self.prompt_to_cid[prompt_id]]\
            .get('prompts', {}).get(prompt_id, {})
        if not prompt_data:
            self.log.error(f"prompt data unexpectedly None for id={prompt_id}")
            return
        if user not in prompt_data['participating_subminds']:
            self.log.warning(f"{user} is not participating in this prompt")
            return
        if user in prompt_data["cycles"][-1]['discussion'][-1]:
            # Users can only send one discussion message per round. Use this
            # repeated user as a signal that a new round of discussion started
            self.log.debug(f"{user} has started a new round of discussion")
            prompt_data["cycles"][-1]['discussion'].append({})
        prompt_data["cycles"][-1]['discussion'][-1][user] = shout

    def on_vote(self, prompt_id: str, selected: str, voter: str):
        if prompt_id not in self.prompt_to_cid:
            self.log.warning(f"Unknown prompt id: {prompt_id}")
            return
        prompt_data = self.current_conversations[self.prompt_to_cid[prompt_id]]\
            .get('prompts', {}).get(prompt_id, {})
        if not prompt_data:
            self.log.error(f"prompt data unexpectedly None for id={prompt_id}")
            return
        if voter not in prompt_data['participating_subminds']:
            self.log.warning(f"{voter} is not participating in this prompt")
            return
        prompt_data["cycles"][-1]['votes'][voter] = selected
        self.log.debug(f"Received vote from {voter}: {selected}")

    def on_selection(self, prompt_id: str, user: str, response: str):
        if prompt_id not in self.prompt_to_cid:
            self.log.warning(f"Unknown prompt id: {prompt_id}")
            return
        cid = self.prompt_to_cid[prompt_id]
        current_prompt = self.current_conversations[cid]['prompts'][prompt_id]
        current_prompt["response"] = response
        current_prompt["winner"] = user
        self.log.info(f"Completed prompt: {current_prompt}")

    # TODO: Implement below methods in place of handling in `get_chatbot_response`
    def on_ready_for_next(self, user: str):
        pass

    def at_chatbot(self, user: str, shout: str, timestamp: str) -> str:
        pass

    def ask_chatbot(self, user: str, shout: str, timestamp: str, context: dict = None) -> str:
        pass

    def ask_appraiser(self, options: dict, context: dict = None) -> str:
        pass

    def ask_discusser(self, options: dict, context: dict = None) -> str:
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
        while next_message_data := self.shout_queue.get():
            self.handle_shout(next_message_data)

    def _pause_responses(self, duration: int = 5):
        pass

    def stop_shout_thread(self):
        if self.shout_thread:
            self.shout_thread.cancel()
            self.shout_thread = None

    def shutdown(self):
        self.shout_thread.cancel()
        self.shout_thread.join()

    def stop(self):
        self.stop_shout_thread()
        KlatAPIMQ.stop(self)

# Unimplemented Abstract Methods
    def _send_first_prompt(self):
        pass

    def ask_history(self, user: str, shout: str, dom: str, cid: str) -> str:
        pass

    def ask_proctor(self, prompt: str, user: str, cid: str, dom: str):
        pass

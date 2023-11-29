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

import random
import re
from abc import abstractmethod
from queue import Queue
from typing import Optional
import time
# import sys
from copy import deepcopy

from engineio.socket import Socket
# import threading
from threading import Thread, Event

from klat_connector.klat_api import KlatApi
from klat_connector import start_socket
from chatbot_core.utils import init_message_bus, make_logger, ConversationState,ConversationControls,\
    remove_prefix, generate_random_response, BotTypes
from chatbot_core.chatbot_abc import ChatBotABC
from chatbot_core.utils.logger import LOG
from mycroft_bus_client import Message, MessageBusClient
from nltk.translate.bleu_score import sentence_bleu
from nltk import word_tokenize
import jellyfish
import spacy

try:
    from autocorrect import Speller

    spell = Speller()
except ImportError:
    LOG.error("autocorrect module not available. Install "
              "`chatbot-core[extra-lgpl]` to use autocorrect.")
    spell = None


class ChatBot(KlatApi, ChatBotABC):
    def __init__(self, *args, **kwargs):
        socket, domain, username, password, on_server, is_prompter = self.parse_init(*args, **kwargs)
        socket = socket or start_socket()
        init_nick = "Prompter" if is_prompter else ""
        KlatApi.__init__(self, socket, domain, init_nick)
        ChatBotABC.__init__(self)
        # self.log.debug("Connector started")
        self.on_server = on_server
        self.is_prompter = is_prompter
        self.start_domain = domain
        self.enable_responses = False
        self.bot_type = None
        self.proposed_responses = dict()
        self.selected_history = list()

        self.username = username
        self.password = password

        self.facilitator_nicks = ["proctor", "scorekeeper", "stenographer"]
        self.response_probability = 75  # % probability for a bot to respond to an input in non-proctored conversation

        # Do klat initialization
        klat_timeout = time.time() + 30
        while not self.ready and time.time() < klat_timeout:
            time.sleep(1)
        if not self.ready:
            self.log.error("Klat connection timed out!")
        elif username and password:
            self.login_klat(username, password)
            while self.logged_in != 2 and time.time() < klat_timeout:
                time.sleep(1)
        else:
            self.enable_responses = True
            self.log.debug(f"Responses enabled for {self.nick}")
            self.on_login()
        self.active_prompt = None
        self.prompt_id = None
        self.id_to_prompt = dict()
        self.state = ConversationState.IDLE
        self.request_history = list()
        self.participant_history = [set()]

        self.initial_prompt = "Hello."
        self.fallback_responses = ("Huh?",
                                   "What?",
                                   "I don't know.",
                                   "I'm not sure what to say to that.",
                                   "I can't respond to that.",
                                   "...",
                                   "Sorry?",
                                   "Come again?")

        self.shout_thread = Thread(target=self._handle_next_shout, daemon=True)
        self.shout_thread.start()

    def parse_init(self, *args, **kwargs) -> tuple:
        """Parses dynamic params input to ChatBot v1"""
        socket, domain, username, password, on_server, is_prompter = (list(args) + [None] * 6)[:6]
        socket: Socket = socket or kwargs.get('socket', None)
        domain: str = domain or kwargs.get('domain', "chatbotsforum.org")
        username: str = username or kwargs.get('username', None)
        password: str = password or kwargs.get('password', None)
        on_server: bool = on_server or kwargs.get('on_server', True)
        is_prompter: bool = is_prompter or kwargs.get('is_prompter', False)
        return socket, domain, username, password, on_server, is_prompter

    def handle_login_return(self, status):
        # self.log.debug(f"login returned: {status}")

        if status == 888:
            self.enable_responses = False
            self.log.info(f"New user, registering {self.username}")
            self.register_klat(self.username, self.password)
        elif status == 999:
            self.log.error(f"Incorrect Password!")
        elif status == 777:
            self.log.error(f"User already logged in and was logged out!")
        elif status == 666:
            self.log.error(f"Nickname in use")
        elif status == 555:
            self.log.error("Old nick not found!")
        elif status != 0:
            self.log.error(f"Unknown error {status} occurred while logging in!")
        self.enable_responses = True
        if not self.nick:
            self.log.error(f"No nick!! expected: {self.username}")
        else:
            self.log.debug(f"Responses enabled for {self.nick}")
        self.change_domain(self.start_domain)
        self.on_login()

    def handle_incoming_shout(self, user: str, shout: str, cid: str, dom: str, timestamp: str):
        """
        Handles an incoming shout into the current conversation
        :param user: user associated with shout
        :param shout: text shouted by user
        :param cid: cid shout belongs to
        :param dom: domain conversation belongs to
        :param timestamp: formatted timestamp of shout
        """
        self.shout_queue.put((user, shout, cid, dom, timestamp))

    def handle_shout(self, user: str, shout: str, cid: str, dom: str, timestamp: str):
        """
        Handles an incoming shout into the current conversation
        :param user: user associated with shout
        :param shout: text shouted by user
        :param cid: cid shout belongs to
        :param dom: domain conversation belongs to
        :param timestamp: formatted timestamp of shout
        """
        if not shout:
            self.log.error(f"No shout (user={user}")
            return
        if not self.nick:
            self.log.error(f"No nick! user is {self.username}")
            return
        if not self.conversation_is_proctored and not self.is_prompter:
            self.log.warning("Un-proctored conversation!!")
        # if not self.is_current_cid(cid):

        # Handle @user incoming shout
        if shout.lower().startswith(f"@{self.nick.lower()}"):
            try:
                shout = f'{shout.split(" ", 1)[1]}'
            except Exception as e:
                self.log.error(e)
                self.log.error(f'@user error: {shout}')

            if self.bot_type == BotTypes.PROCTOR:
                self.log.info("@Proctor shout incoming")
                try:
                    self.ask_proctor(shout, user, cid, dom)
                except Exception as e:
                    self.log.error(e)
                    self.log.error(f'Ignoring incoming: {shout}')
            elif self.bot_type == BotTypes.OBSERVER:
                self.log.info("@observer shout incoming")
                # TODO: Consider something here DM
                # try:
                #     shout = f'{shout.split(" ", 1)[1]}'
                # except Exception as e:
                #     self.log.error(e)
                #     self.log.error(f'Ignoring incoming: {shout}')
            elif self.bot_type == BotTypes.SUBMIND:
                self.log.info(f"@bot shout incoming")
                resp = self.at_chatbot(user, shout, timestamp)
                if self.is_prompter:
                    self.log.info(f"Prompter bot got reply: {shout}")
                    # private_cid = self.get_private_conversation([user])
                    self.send_shout(resp)
                    return
        # Ignore anything from a different conversation that isn't @ this bot
        elif not self.is_current_cid(cid):
            if self.bot_type == BotTypes.PROCTOR and self._user_is_prompter(user):
                self.ask_proctor(shout, user, cid, dom)
            else:
                self.log.warning(f"Crossposted shout ignored ({cid} != {self._cid}|user={user})")
            return
        # Ignore anything that is @ a different user
        elif shout.startswith("@"):
            self.log.debug(f"Outgoing shout ignored ({shout})")
            return
        # Handle a proctor response to a prompter
        elif self._user_is_proctor(user) and self.is_prompter:
            resp = self.at_chatbot(user, shout, timestamp)
            if self.is_prompter:
                self.log.info(f"Prompter bot got reply: {shout}")
                # private_cid = self.get_private_conversation([user])
                self.send_shout(resp)
                return
        # Subminds ignore facilitators
        elif not self._user_is_proctor(user) and user.lower() in self.facilitator_nicks \
                and self.bot_type == BotTypes.SUBMIND:
            self.log.debug(f"{self.nick} ignoring facilitator shout: {shout}")
        # Cleanup nick for comparison to logged in user
        if "#" in user:
            user = user.split("#")[0]

        # Handle prompts with incorrect prefix case
        if not shout.startswith("!PROMPT:") and shout.lower().startswith("!prompt:"):
            content = shout.split(':', 1)[1].strip()
            self.log.info(f"Cleaned Prompt={content}")
            shout = f"!PROMPT:{content}"

        # Handle Parsed Shout
        try:
            # Proctor Control Messages
            if shout.endswith(ConversationControls.WAIT) and self._user_is_proctor(user):  # Notify next prompt bots
                participants = shout[:-len(ConversationControls.WAIT)]
                participants = set(participant.lower().strip() for participant in participants.split(","))
                self.participant_history.append(participants)

                if self.bot_type == BotTypes.SUBMIND and self.nick.lower() not in re.split("[, ]", shout.lower()):
                    self.log.info(f"{self.nick} will sit this round out.")
                    self.state = ConversationState.WAIT
                else:
                    self.log.info(f"{self.nick} will participate in the next round.")
                    self.state = ConversationState.IDLE

                if self.bot_type == BotTypes.SUBMIND:  # Only subminds need to be ready for the next prompt
                    self.send_shout(ConversationControls.NEXT)
            elif self.state == ConversationState.WAIT and self.bot_type == BotTypes.SUBMIND:
                self.log.debug(f"{self.nick} is sitting this round out!")
            elif shout.startswith(ConversationControls.DISC) and self._user_is_proctor(user):  # Discuss Options
                self.state = ConversationState.DISC
                start_time = time.time()
                options: dict = deepcopy(self.proposed_responses[self.active_prompt])
                discussion = self.ask_discusser(options)
                if discussion:
                    self._hesitate_before_response(start_time=start_time)
                    self.discuss_response(discussion)
            elif shout.startswith(ConversationControls.VOTE) and self._user_is_proctor(user):  # Vote
                self.state = ConversationState.VOTE
                if self.bot_type == BotTypes.SUBMIND:  # Facilitators don't participate here
                    start_time = time.time()
                    options: dict = self._clean_options()
                    selected = self.ask_appraiser(options)
                    self._hesitate_before_response(start_time)
                    if not selected or selected == self.nick:
                        selected = "abstain"
                    self.vote_response(selected)
            elif shout.startswith(ConversationControls.PICK) and self._user_is_proctor(user):  # Voting is closed
                self.state = ConversationState.PICK

            # Commands
            elif ConversationControls.HIST in shout.lower():  # User asked for history
                response = self.ask_history(user, shout, dom, cid)
                if response:
                    if not self.is_current_cid(cid):
                        response = f"@{user} {response}"
                    self.send_shout(response, cid, dom)

            # Incoming prompt
            elif self._shout_is_prompt(shout) and self.conversation_is_proctored:
                # self.state = ConversationState.RESP
                # self.active_prompt = remove_prefix(shout, "!PROMPT:")
                if self.bot_type == BotTypes.PROCTOR:
                    self.log.debug(f"Incoming prompt: {shout}")
                    try:
                        self.ask_proctor(remove_prefix(shout, "!PROMPT:"), user, cid, dom)
                    except Exception as x:
                        self.log.error(f"{self.nick} | {x}")
                # else:
                #     self.log.debug(f"{self.nick} Ignoring incoming Proctor Prompt")
                # self.ask_chatbot(user, self.active_prompt, timestamp)
            elif self.state == ConversationState.IDLE and self._user_is_proctor(user) \
                    and ConversationControls.RESP in shout:
                try:
                    self.state = ConversationState.RESP
                    request_user, remainder = shout.split(ConversationControls.RESP, 1)
                    request_user = request_user.strip()
                    self.active_prompt = remainder.rsplit("(", 1)[0].strip().strip('"')
                    self.prompt_id = str(round(time.time()))
                    self.id_to_prompt[self.prompt_id] = self.active_prompt
                    self.log.debug(f"Got prompt: {self.active_prompt}")
                    self.request_history.append((request_user, self.active_prompt))
                    self.log.debug(self.request_history)
                    # if len(self.request_history) != len(self.participant_history):
                    #     LOG.error(self.request_history)
                    #     LOG.error(self.participant_history)
                    # if request_user in self.chat_history.keys():
                    #     self.chat_history[request_user].append(self.active_prompt)
                    # else:
                    #     self.chat_history[request_user] = [self.active_prompt]
                    self.proposed_responses[self.active_prompt] = {}
                    self.log.debug(self.proposed_responses)
                    start_time = time.time()
                    try:
                        response = self.ask_chatbot(request_user, self.active_prompt, timestamp)
                    except Exception as x:
                        self.log.error(x)
                        response = None
                    self._hesitate_before_response(start_time)
                    self.propose_response(response)
                except Exception as e:
                    self.log.error(e)
                    self.log.error(shout)
                    self.state = ConversationState.IDLE

            # Chatbot communication related to a prompt
            elif self.state == ConversationState.RESP and not self._user_is_proctor(user):
                self.add_proposed_response(user, self.active_prompt, shout)
            elif self.state == ConversationState.DISC and not self._user_is_proctor(user):
                if user != self.nick:
                    try:
                        self.on_discussion(user, shout)
                    except Exception as x:
                        self.log.error(f"{self.nick} | {x}")
            elif self.state == ConversationState.VOTE and user.lower() not in self.facilitator_nicks:
                candidate_bot = None
                for candidate in self.conversation_users:
                    if candidate.lower() in shout.lower().split():
                        candidate_bot = candidate
                        if self.bot_type == BotTypes.PROCTOR:
                            self.log.debug(f"{user} votes for {candidate_bot}")
                        self.on_vote(self.prompt_id, candidate_bot, user)
                        break
                if not candidate_bot:
                    # Keywords to indicate user will not vote
                    if "abstain" in shout.split() or "present" in shout.split():
                        self.on_vote(self.prompt_id, "abstain", user)
                    else:
                        self.log.warning(f"No valid vote cast! {shout}")
            elif self.state == ConversationState.PICK and self._user_is_proctor(user):
                try:
                    user, response = shout.split(":", 1)
                    user = user.split()[-1]
                    response = response.strip().strip('"')
                    self.selected_history.append(user.lower())
                    self.on_selection(self.active_prompt, user, response)
                    if self.nick.lower() == "scorekeeper":  # Get the history (for scorekeeper)
                        history = self.ask_history(user, shout, dom, cid)
                        self.send_shout(history, cid, dom)
                except Exception as x:
                    self.log.error(x)
                    self.log.error(shout)
                self.state = ConversationState.IDLE
                self.active_prompt = None
                self.prompt_id = None
                # if self.bot_type == "submind":  # Only subminds need to be ready for the next prompt
                #     self.send_shout(ConversationControls.NEXT)
            elif shout == ConversationControls.NEXT:
                self.on_ready_for_next(user)
            # This came from a different non-neon user and is not related to a proctored conversation
            elif user.lower() not in ("neon", self.nick.lower(), None) and self.enable_responses:
                if self.bot_type == BotTypes.SUBMIND:
                    self.log.debug(f"{self.nick} handling {shout}")
                    # Submind handle prompt
                    if not self.conversation_is_proctored:
                        if shout.startswith("!PROMPT:"):
                            self.log.error(f"Prompt into unproctored conversation! {shout}")
                            return
                        try:
                            if random.randint(1, 100) < self.response_probability:
                                response = self.ask_chatbot(user, shout, timestamp)
                                self.propose_response(response)
                            else:
                                self.log.info(f"{self.nick} ignoring input: {shout}")
                        except Exception as x:
                            self.log.error(f"{self.nick} | {x}")
                elif self.bot_type in (BotTypes.PROCTOR, BotTypes.OBSERVER):
                    pass
                else:
                    self.log.error(f"{self.nick} has unknown bot type: {self.bot_type}")
        except Exception as e:
            self.log.error(e)
            self.log.error(f"{self.nick} | {shout}")
        # else:
        #     self.log.debug(f"{self.nick} Ignoring: {user} - {shout}")

    def add_proposed_response(self, user, prompt, response):
        """
        Add a proposed response to be evaluated when all proposals are in
        :param user: username associated with proposed response
        :param prompt: prompt associated with response
        :param response: bot response to prompt
        """
        if response and response != self.active_prompt:
            # if prompt in self.proposed_responses.keys():
            self.proposed_responses[prompt][user.lower()] = response
            # else:
            #     self.proposed_responses[prompt] = {user: response}
        self.on_proposed_response()

    # Submind Functions
    def propose_response(self, shout: str):
        """
        Called when a bot as a proposed response to the input prompt
        :param shout: Proposed response to the prompt
        """
        # Generate a random response if none is provided
        if shout == self.active_prompt:
            self.log.info(f"Pick random response for {self.nick}")
            shout = generate_random_response(self.fallback_responses)

        if not shout:
            if self.bot_type == BotTypes.SUBMIND:
                self.log.warning(f"Empty response provided! ({self.nick})")
        elif not self.conversation_is_proctored:
            self.send_shout(shout)
            self._pause_responses(len(self.conversation_users) * 5)
        elif self.state == ConversationState.RESP:
            self.send_shout(shout)
        elif self.state == ConversationState.VOTE:
            self.log.warning(f"Late Response! {shout}")
        else:
            self.log.error(f"Unknown response error! Ignored: {shout}")

        if not self.enable_responses:
            self.log.warning(f"re-enabling responses!")
            self.enable_responses = True

    def discuss_response(self, shout: str):
        """
        Called when a bot has some discussion to share
        :param shout: Response to post to conversation
        """
        if self.state != ConversationState.DISC:
            self.log.warning(f"Late Discussion! {shout}")
        elif not shout:
            self.log.warning(f"Empty discussion provided! ({self.nick})")
        else:
            self.send_shout(shout)

    def vote_response(self, response_user: str, cid: str = None):
        """
            Called when a bot appraiser has selected a response
            :param response_user: bot username associated with chosen response
            :param cid: dedicated conversation id (optional)
        """
        if self.state != ConversationState.VOTE:
            self.log.warning(f"Late Vote! {response_user}")
            return None
        elif not response_user:
            self.log.error("Null response user returned!")
            return None
        elif response_user in (self.nick, "abstain"):
            # self.log.debug(f"Abstaining voter! ({self.nick})")
            self.send_shout("I abstain from voting.")
            return "abstain"
        else:
            self.send_shout(f"I vote for {response_user}")
            return response_user

    def on_login(self):
        """
        Override to execute any initialization after logging in or after connection if no username/password
        """
        pass

    def on_vote(self, prompt_id: str, selected: str, voter: str):
        """
        Override in any bot to handle counting votes. Proctors use this to select a response.
        :param prompt_id: id of prompt being voted on
        :param selected: bot username voted for
        :param voter: user who voted
        """
        pass

    def on_discussion(self, user: str, shout: str):
        """
        Override in any bot to handle discussion from other subminds. This may inform voting for the current prompt
        :param user: user associated with shout
        :param shout: shout to be considered
        """
        pass

    def on_proposed_response(self):
        """
        Override in Proctor to check when to notify bots to vote
        """
        pass

    def on_selection(self, prompt: str, user: str, response: str):
        """
        Override in any bot to handle a proctor selection of a response
        :param prompt: input prompt being considered
        :param user: user who proposed selected response
        :param response: selected response to prompt
        """
        pass

    def on_ready_for_next(self, user: str):
        """
        Notifies when a bot is finished handling the current prompt and is ready for the next one. This should happen
        shortly after the proctor selects a response.
        :param user: user who is ready for the next prompt
        """
        pass

    def at_chatbot(self, user: str, shout: str, timestamp: str) -> str:
        """
        Override in subminds to handle an incoming shout that is directed at this bot. Defaults to ask_chatbot.
        :param user: user associated with shout
        :param shout: text shouted by user
        :param timestamp: formatted timestamp of shout
        :return: response from chatbot
        """
        return self.ask_chatbot(user, shout, timestamp)

    def ask_proctor(self, prompt: str, user: str, cid: str, dom: str):
        """
        Override in proctor to handle a new prompt to queue
        :param prompt: Cleaned prompt for discussion
        :param user: user associated with prompt
        :param cid: cid prompt is from
        :param dom: dom prompt is from
        """
        pass

    def ask_chatbot(self, user: str, shout: str, timestamp: str) -> str:
        """
        Override in subminds to handle an incoming shout that requires some response. If no response can be determined,
        return the prompt.
        :param user: user associated with shout
        :param shout: text shouted by user
        :param timestamp: formatted timestamp of shout
        :return: response from chatbot
        """
        pass

    def ask_history(self, user: str, shout: str, dom: str, cid: str) -> str:
        """
        Override in scorekeepers to handle an incoming request for the selection history
        :param user: user associated with request
        :param shout: shout requesting history
        :param dom: domain user shout originated from
        :param cid: conversation user shout originated from
        :return: Formatted string response
        """
        pass

    def ask_appraiser(self, options: dict) -> str:
        """
        Override in bot to handle selecting a response to the given prompt. Vote is for the name of the best responder.
        :param options: proposed responses (botname: response)
        :return: user selected from options or "abstain" for no vote
        """
        pass

    def ask_discusser(self, options: dict) -> str:
        """
        Override in bot to handle discussing options for the given prompt. Discussion can be anything.
        :param options: proposed responses (botname: response)
        :return: Discussion response for the current prompt
        """
        pass

    @staticmethod
    def _user_is_proctor(nick):
        """
        Determines if the passed nick is a proctor.
        :param nick: nick to check
        :return: true if nick belongs to a proctor
        """
        return "proctor" in nick.lower()

    @staticmethod
    def _user_is_prompter(nick):
        """
        Determines if the passed nick is a proctor.
        :param nick: nick to check
        :return: true if nick belongs to a proctor
        """
        return nick.lower() == "prompter"

    @staticmethod
    def _shout_is_prompt(shout):
        """
        Determines if the passed shout is a new prompt for the proctor.
        :param shout: incoming shout
        :return: true if shout should be considered a prompt
        """
        return shout.startswith("!PROMPT:")

    def _clean_options(self):
        """
        Gets a dict of options with the
        """
        return {nick.lower(): resp for nick, resp in self.proposed_responses[self.active_prompt].items()
                if nick.lower() != self.nick.lower() and resp != self.active_prompt}

    def _pause_responses(self, duration: int = 5):
        """
        Pauses generation of bot responses
        :param duration: seconds to pause
        """
        self.enable_responses = False
        time.sleep(duration)
        self.enable_responses = True

    def _handle_next_shout(self):
        """
        Called recursively to handle incoming shouts synchronously
        """
        next_shout = self.shout_queue.get()
        while next_shout:
            # (user, shout, cid, dom, timestamp)
            self.handle_shout(next_shout[0], next_shout[1], next_shout[2], next_shout[3], next_shout[4])
            next_shout = self.shout_queue.get()
        self.log.warning(f"No next shout to handle! No more shouts will be processed by {self.nick}")
        self.exit()

    def _send_first_prompt(self):
        """
        Sends an initial prompt to the proctor for a prompter bot
        """
        self.log.debug(f"{self.nick} sending initial prompt!")
        self.send_shout("@Proctor hello!", self.get_private_conversation(["Proctor"]), "Private")

    def exit(self):
        from chatbot_core.utils import clean_up_bot
        # import sys
        # self.socket.disconnect()
        while not self.shout_queue.empty():
            self.shout_queue.get(timeout=1)
        clean_up_bot(self)
        # self.shout_queue.put(None)
        # self.log.warning(f"EXITING")
        # sys.exit()


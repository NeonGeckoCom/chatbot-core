# NEON AI (TM) SOFTWARE, Software Development Kit & Application Development System
#
# Copyright 2008-2020 Neongecko.com Inc. | All Rights Reserved
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
# US Patents 2008-2020: US7424516, US20140161250, US20140177813, US8638908, US8068604, US8553852, US10530923, US10530924
# China Patent: CN102017585  -  Europe Patent: EU2156652  -  Patents Pending

import random
from queue import Queue
from typing import Optional

import time

from copy import deepcopy
from enum import IntEnum

from engineio.socket import Socket
import threading
from threading import Thread

from klat_connector.klat_api import KlatApi
from klat_connector import start_socket  # Leave for extending classes to use without explicit klat_connector import
from chatbot_core.logger import make_logger
from mycroft_bus_client import Message, MessageBusClient
from autocorrect import Speller

LOG = make_logger("chatbot")


def childmost(decorator_func):
    """
    Method used to constraint decorator evaluation to childmost derived instance
    :param decorator_func: decorator to consider
    Source:
    https://stackoverflow.com/questions/57104276/python-subclass-method-to-inherit-decorator-from-superclass-method
    """

    def inheritable_decorator_that_runs_once(func):
        decorated_func = decorator_func(func)
        name = func.__name__

        def wrapper(self, *args, **kw):
            if not hasattr(self, f"_running_{name}"):
                setattr(self, f"_running_{name}", threading.local())
            running_registry = getattr(self, f"_running_{name}")
            try:
                if not getattr(running_registry, "running", False):
                    running_registry.running = True
                    rt = decorated_func(self, *args, **kw)
                else:
                    rt = func(self, *args, **kw)
            finally:
                running_registry.running = False
            return rt

        wrapper.inherit_decorator = inheritable_decorator_that_runs_once
        return wrapper

    return inheritable_decorator_that_runs_once


@childmost
def grammar_check(func):
    """
    Checks grammar for output of passed function
    :param func: function to consider
    """
    spell = Speller()

    def wrapper(*args, **kwargs):
        LOG.debug("Entered decorator")
        output = func(*args, **kwargs)
        if output:
            LOG.debug(f"Received output: {output}")
            output = spell(output)
            LOG.debug(f"Processed output: {output}")
        return output

    return wrapper


class InheritDecoratorsMixin:
    """
    Mixin for allowing usage of superclass method decorators.
    Source:
    https://stackoverflow.com/questions/57104276/python-subclass-method-to-inherit-decorator-from-superclass-method
    """

    def __init_subclass__(cls, *args, **kwargs):
        super().__init_subclass__(*args, **kwargs)
        decorator_registry = getattr(cls, "_decorator_registry", {}).copy()
        cls._decorator_registry = decorator_registry
        # Check for decorated objects in the mixin itself- optional:
        for name, obj in __class__.__dict__.items():
            if getattr(obj, "inherit_decorator", False) and not name in decorator_registry:
                decorator_registry[name] = obj.inherit_decorator
        # annotate newly decorated methods in the current subclass:
        for name, obj in cls.__dict__.items():
            if getattr(obj, "inherit_decorator", False) and not name in decorator_registry:
                decorator_registry[name] = obj.inherit_decorator
        # finally, decorate all methods anottated in the registry:
        for name, decorator in decorator_registry.items():
            if name in cls.__dict__ and getattr(getattr(cls, name), "inherit_decorator", None) != decorator:
                setattr(cls, name, decorator(cls.__dict__[name]))


class ConversationControls:
    RESP = " asks us to consider:"
    DISC = "Please Discuss"
    VOTE = "Voting on the response to "
    PICK = "Tallying the votes for the responses to "
    NEXT = "I'm ready for the next prompt."
    HIST = "history"
    WAIT = " may respond to the next prompt."


class ConversationState(IntEnum):
    IDLE = 0  # No active prompt
    RESP = 1  # Gathering responses to prompt
    DISC = 2  # Discussing responses
    VOTE = 3  # Voting on responses
    PICK = 4  # Proctor will select response
    WAIT = 5  # Bot is waiting for the proctor to ask them to respond (not participating)


class ChatBot(KlatApi, InheritDecoratorsMixin):
    def __init__(self, socket: Socket, domain: str = "chatbotsforum.org",
                 username: str = None, password: str = None, on_server: bool = True):
        super(ChatBot, self).__init__(socket, domain)
        global LOG
        # self.log.debug("Connector started")
        self.on_server = on_server
        self.start_domain = domain
        self.enable_responses = False
        self.bot_type = None
        self.proposed_responses = dict()
        self.selected_history = list()
        self.shout_queue = Queue(maxsize=256)

        self.username = username
        self.password = password

        self.log = make_logger(self.__class__.__name__)
        self.log.setLevel(LOG.level)
        LOG = self.log

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
        self.state = ConversationState.IDLE
        self.request_history = list()
        self.participant_history = [tuple()]

        self.fallback_responses = ("Huh?",
                                   "What?",
                                   "I don't know.",
                                   "I'm not sure what to say to that.",
                                   "I can't respond to that.",
                                   "...",
                                   "Sorry?",
                                   "Come again?")
        self.shout_thread = Thread(target=self._handle_next_shout)
        self.shout_thread.start()

    def handle_login_return(self, status):
        # self.log.debug(f"login returned: {status}")

        if status == 888:
            LOG.info(f"New user, registering {self.username}")
            self.register_klat(self.username, self.password)
        elif status == 999:
            LOG.error(f"Incorrect Password!")
        # elif status == 666:
        #     LOG.error(f"Nickname in use")
        elif status != 0:
            LOG.error(f"Error {status} occurred while logging in!")
        # TODO: Catch and log other non-success returns!!
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
        if not self.conversation_is_proctored:
            self.log.warning("Un-proctored conversation!!")
        # if not self.is_current_cid(cid):

        # Handle @user incoming shout
        if shout.lower().startswith(f"@{self.nick.lower()}"):
            if self.bot_type == "proctor":
                self.log.info("@Proctor shout incoming")
                try:
                    shout = f'!PROMPT:{shout.split(" ", 1)[1]}'
                except Exception as e:
                    self.log.error(e)
                    self.log.error(f'Ignoring incoming: {shout}')
            elif self.bot_type == "observer":
                self.log.info("@observer shout incoming")
                try:
                    shout = f'{shout.split(" ", 1)[1]}'
                except Exception as e:
                    self.log.error(e)
                    self.log.error(f'Ignoring incoming: {shout}')
            elif self.bot_type == "submind":
                self.log.info(f"@bot shout incoming")
                self.at_chatbot(user, shout, timestamp)
        # Ignore anything from a different conversation that isn't @ this bot
        elif not self.is_current_cid(cid):
            self.log.warning(f"Crossposted shout ignored ({cid} != {self._cid})")
            return
        # Ignore anything that is @ a different user
        elif shout.startswith("@"):
            self.log.debug(f"Outgoing shout ignored ({shout})")
            return
        # Subminds ignore facilitators
        elif user.lower() != "proctor" and user.lower() in self.facilitator_nicks and self.bot_type == "submind":
            self.log.info(f"{self.nick} ignoring facilitator shout: {shout}")
        # Cleanup nick for comparison to logged in user
        if "#" in user:
            user = user.split("#")[0]

        # Handle prompts with incorrect prefix case
        if not shout.startswith("!PROMPT:") and shout.lower().startswith("!prompt:"):
            content = shout.split(':', 1)[1].strip()
            LOG.info(f"Cleaned Prompt={content}")
            shout = f"!PROMPT:{content}"

        # Handle Parsed Shout
        try:
            # Proctor Control Messages
            if shout.endswith(ConversationControls.WAIT) and self._user_is_proctor(user):  # Notify next prompt bots
                participants = shout.rstrip(ConversationControls.WAIT)
                participants = (participant.lower().strip() for participant in participants.split(","))
                self.participant_history.append(participants)

                if self.bot_type == "submind" and self.nick.lower() not in shout.lower():
                    self.log.info(f"{self.nick} will sit this round out.")
                    self.state = ConversationState.WAIT
                else:
                    self.log.info(f"{self.nick} will participate in the next round.")
                    self.state = ConversationState.IDLE

                if self.bot_type == "submind":  # Only subminds need to be ready for the next prompt
                    self.send_shout(ConversationControls.NEXT)
            elif self.state == ConversationState.WAIT and self.bot_type == "submind":
                self.log.debug(f"{self.nick} is sitting this round out!")
            elif shout.startswith(ConversationControls.DISC) and self._user_is_proctor(user):  # Discuss Options
                self.state = ConversationState.DISC
                start_time = time.time()
                options: dict = deepcopy(self.proposed_responses[self.active_prompt])
                discussion = self.ask_discusser(options)
                if discussion:
                    self._hesitate_before_response(start_time)
                    self.discuss_response(discussion)
            elif shout.startswith(ConversationControls.VOTE) and self._user_is_proctor(user):  # Vote
                self.state = ConversationState.VOTE
                if self.bot_type == "submind":  # Facilitators don't participate here
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
                # self.active_prompt = self._remove_prefix(shout, "!PROMPT:")
                if self.bot_type == "proctor":
                    self.log.debug(f"Incoming prompt: {shout}")
                    try:
                        self.ask_proctor(self._remove_prefix(shout, "!PROMPT:"), user, cid, dom)
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
                    self.log.debug(f"Got prompt: {self.active_prompt}")
                    self.request_history.append((request_user, self.active_prompt))
                    self.log.debug(self.request_history)
                    if len(self.request_history) != len(self.participant_history):
                        LOG.error(self.request_history)
                        LOG.error(self.participant_history)
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
                    if candidate in shout.split():
                        candidate_bot = candidate
                        if self.bot_type == "proctor":
                            self.log.debug(f"{user} votes for {candidate_bot}")
                        self.on_vote(self.active_prompt, candidate_bot, user)
                        break
                if not candidate_bot:
                    # Keywords to indicate user will not vote
                    if "abstain" in shout.split() or "present" in shout.split():
                        self.on_vote(self.active_prompt, "abstain", user)
                    else:
                        self.log.warning(f"No valid vote cast! {shout}")
            elif self.state == ConversationState.PICK and self._user_is_proctor(user):
                try:
                    user, response = shout.split(":", 1)
                    user = user.split()[-1]
                    response = response.strip().strip('"')
                    self.selected_history.append(user)
                    self.on_selection(self.active_prompt, user, response)
                    if self.nick.lower() == "scorekeeper":  # Get the history (for scorekeeper)
                        history = self.ask_history(user, shout, dom, cid)
                        self.send_shout(history, cid, dom)
                except Exception as x:
                    self.log.error(x)
                    self.log.error(shout)
                self.state = ConversationState.IDLE
                self.active_prompt = None
                # if self.bot_type == "submind":  # Only subminds need to be ready for the next prompt
                #     self.send_shout(ConversationControls.NEXT)
            elif shout == ConversationControls.NEXT:
                self.on_ready_for_next(user)
            # This came from a different non-neon user and is not related to a proctored conversation
            elif user.lower() not in ("neon", self.nick.lower(), None) and self.enable_responses:
                if self.bot_type == "submind":
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
                elif self.bot_type in ("proctor", "observer"):
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
            self.proposed_responses[prompt][user] = response
            # else:
            #     self.proposed_responses[prompt] = {user: response}
        self.on_proposed_response()

    # Proctor Functions
    def call_discussion(self, timeout: int):
        """
        Called by proctor to ask all subminds to discuss a response
        """
        self.state = ConversationState.DISC
        self.send_shout(f"{ConversationControls.DISC} \"{self.active_prompt}\" for {timeout} seconds.")

    def call_voting(self, timeout: int):
        """
        Called by proctor to ask all subminds to vote on a response
        """
        self.state = ConversationState.VOTE
        self.send_shout(f"{ConversationControls.VOTE} \"{self.active_prompt}\" for {timeout} seconds.")

    def close_voting(self):
        """
        Called by proctor to announce to all subminds that voting is over and the response will be selected
        """
        self.state = ConversationState.PICK
        self.send_shout(f"{ConversationControls.PICK} \"{self.active_prompt}\"")

    def pick_respondents(self, bots: list):
        """
        Called by proctor to select which bots may respond to the next prompt
        """
        bot_str = ",".join(bots)
        self.send_shout(f"{bot_str}{ConversationControls.WAIT}")

    def announce_selection(self, user: str, selection: str):
        """
        Called by proctor to announce the selected user and response
        """
        self.send_shout(f"The selected response is from {user}: \"{selection}\"")

    # Submind Functions
    def propose_response(self, shout: str):
        """
        Called when a bot as a proposed response to the input prompt
        :param shout: Proposed response to the prompt
        """
        # Generate a random response if none is provided
        if shout == self.active_prompt:
            self.log.info(f"Pick random response for {self.nick}")
            shout = self._generate_random_response()

        if not shout:
            if self.bot_type == "submind":
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

    def vote_response(self, response_user: str):
        """
        Called when a bot appraiser has selected a response
        :param response_user: bot username associated with chosen response
        """
        if self.state != ConversationState.VOTE:
            self.log.warning(f"Late Vote! {response_user}")
            return None
        elif not response_user:
            self.log.error("Null response user returned!")
            return None
        elif response_user == "abstain" or response_user == self.nick:
            # self.log.debug(f"Abstaining voter! ({self.nick})")
            self.send_shout("I abstain from voting.")
            return "abstain"
        else:
            self.send_shout(f"I vote for {response_user}")
            return response_user

    @grammar_check
    def _generate_random_response(self):
        """
        Generates some random bot response from the given options or the default list
        """
        return random.choice(self.fallback_responses)

    def on_login(self):
        """
        Override to execute any initialization after logging in or after connection if no username/password
        """
        pass

    @grammar_check
    def on_vote(self, prompt: str, selected: str, voter: str):
        """
        Override in any bot to handle counting votes. Proctors use this to select a response.
        :param prompt: prompt being voted on
        :param selected: bot username voted for
        :param voter: user who voted
        """
        pass

    @grammar_check
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

    @grammar_check
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

    @grammar_check
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

    @grammar_check
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

    @grammar_check
    def ask_appraiser(self, options: dict) -> str:
        """
        Override in bot to handle selecting a response to the given prompt. Vote is for the name of the best responder.
        :param options: proposed responses (botname: response)
        :return: user selected from options or "abstain" for no vote
        """
        pass

    @grammar_check
    def ask_discusser(self, options: dict) -> str:
        """
        Override in bot to handle discussing options for the given prompt. Discussion can be anything.
        :param options: proposed responses (botname: response)
        :return: Discussion response for the current prompt
        """
        pass

    @staticmethod
    def _remove_prefix(prefixed_string: str, prefix: str):
        """
        Removes the specified prefix from the string
        :param prefixed_string: raw string to clean
        :param prefix: prefix to remove
        :return: string with prefix removed
        """
        if prefixed_string.startswith(prefix):
            return prefixed_string[len(prefix):]
        return prefixed_string

    @staticmethod
    def _user_is_proctor(nick):
        """
        Determines if the passed nick is a proctor.
        :param nick: nick to check
        :return: true if nick belongs to a proctor
        """
        return nick == "Proctor"

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
        return {nick: resp for nick, resp in self.proposed_responses[self.active_prompt].items()
                if nick != self.nick and resp != self.active_prompt}

    def _pause_responses(self, duration: int = 5):
        """
        Pauses generation of bot responses
        :param duration: seconds to pause
        """
        self.enable_responses = False
        time.sleep(duration)
        self.enable_responses = True

    def _hesitate_before_response(self, start_time):
        if time.time() - start_time < 5:
            # Apply some random wait time if we got a response very quickly
            time.sleep(random.randrange(0, 50) / 10)
        else:
            self.log.debug("Skipping artificial wait!")

    def _handle_next_shout(self):
        """
        Called recursively to handle incoming shouts synchronously
        """
        next_shout = self.shout_queue.get()
        if next_shout:
            # (user, shout, cid, dom, timestamp)
            self.handle_shout(next_shout[0], next_shout[1], next_shout[2], next_shout[3], next_shout[4])
            self._handle_next_shout()
        else:
            self.log.warning(f"No next shout to handle! No more shouts will be processed by {self.nick}")


class NeonBot(ChatBot):
    """
    Extensible class to handle a chatbot implemented in custom-conversations skill
    """

    def __init__(self, socket, domain, username, password, on_server, script, bus_config=None):
        self.bot_type = "submind"
        self.response = None
        self.response_timeout = 15
        self.bus: Optional[MessageBusClient] = None
        self.bus_config = bus_config or {"host": "167.172.112.7",
                                         "port": 8181,
                                         "ssl": False,
                                         "route": "/core"}
        self.script = script
        self.script_ended = False
        self.script_started = False
        self._init_bus()
        self._set_bus_listeners()
        super(NeonBot, self).__init__(socket, domain, username, password, on_server)

        timeout = time.time() + 60
        while not self.script_started and time.time() < timeout:
            time.sleep(1)
        if self.script_started:
            self.log.debug("Neon Bot Started!")
        else:
            self.log.error("Neon Bot Error!")

    def ask_chatbot(self, nick: str, shout: str, timestamp: str):
        """
        Handles an incoming shout into the current conversation
        :param nick: user associated with shout
        :param shout: text shouted by user
        :param timestamp: formatted timestamp of shout
        """
        self.log.debug(f"ask neon: {shout}")
        # shout_time = datetime.datetime.strptime(timestamp, "%I:%M:%S %p")
        # timestamp = round(shout_time.timestamp())
        self.response = None
        self._send_to_neon(shout, timestamp, self.nick)
        # if not self.on_server:
        timeout = time.time() + self.response_timeout
        while not self.response and time.time() < timeout:
            time.sleep(0.5)
        if not self.response:
            self.log.error(f"No response to script input!")
        return self.response or shout

    def on_login(self):
        self.log.debug("NeonBot on_login")
        while not self.bus:
            self.log.error("Bus not configured yet!")
            time.sleep(1)
        while not self.bus.started_running:
            self.log.error("Bus not running yet!")
            time.sleep(1)
        self._send_to_neon("exit", str(round(time.time())), self.nick)
        self.enable_responses = False
        timeout = time.time() + 5
        while not self.script_ended and time.time() < timeout:
            time.sleep(1)
        self._send_to_neon(f"run my {self.script} script", str(round(time.time())), self.nick)

    def _init_bus(self):
        self.bus = MessageBusClient(self.bus_config["host"], self.bus_config["port"],
                                    self.bus_config["route"], self.bus_config["ssl"])
        t = Thread(target=self.bus.run_forever)
        t.daemon = True
        t.start()
        return t

    def _set_bus_listeners(self):
        self.bus.on("speak", self._handle_speak)

    def _handle_speak(self, message: Message):
        """
        Forwards a Neon response into a shout by the logged in user in their current conversation
        :param message: messagebus message associated with "speak"
        """
        self.log.debug(message.context)
        if message.context.get("client") == self.instance:
            input_to_neon = message.context.get("cc_data", {}).get("raw_utterance")
            if input_to_neon == "exit":
                self.script_ended = True
            elif input_to_neon == f"run my {self.script} script":
                time.sleep(5)  # Matches timeout in cc skill for intro speak signal to be cleared
                self.script_started = True
                self.enable_responses = True
            elif input_to_neon and self.enable_responses:
                # self.log.debug(f'sending shout: {message.data.get("utterance")}')
                # if self.on_server:
                #     self.propose_response(message.data.get("utterance"))
                # else:
                self.response = message.data.get("utterance")

    def _send_to_neon(self, shout: str, timestamp: str, nick: str = None):
        """
        Send input to Neon for skills processing
        :param shout: shout to evaluate
        :param timestamp: timestamp of shout
        :param nick: user associated with shout
        """
        nick = nick or "nobody"
        data = {
            "raw_utterances": [shout],
            "utterances": [shout],
            "lang": "en-US",
            "session": "api",
            "user": nick  # This is the user "hosting" this api connection
        }
        context = {'client_name': 'neon_bot',
                   'source': 'klat',
                   "ident": f"chatbots_{timestamp}",
                   'destination': ["skills"],
                   "mobile": False,
                   "client": self.instance,
                   "flac_filename": None,
                   "neon_should_respond": True,
                   "nick_profiles": {},
                   "cc_data": {"speak_execute": shout,
                               "audio_file": None,
                               "raw_utterance": shout
                               },
                   "timing": {"received": time.time()}
                   }
        # Emit to Neon for a response
        self.log.debug(data)
        self.bus.emit(Message("recognizer_loop:utterance", data, context))

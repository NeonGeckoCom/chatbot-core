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

import time

from copy import deepcopy
from enum import IntEnum

from engineio.socket import Socket
from threading import Thread

from klat_connector.klat_api import KlatApi
from klat_connector import start_socket  # Leave for extending classes to use without explicit klat_connector import
from chatbot_core.logger import LOG
from mycroft_bus_client import Message, MessageBusClient


class ConversationControls:
    RESP = " asks us to consider:"
    DISC = "Please Discuss"
    VOTE = "Voting on the response to "
    PICK = "Tallying the votes for the responses to "
    HIST = "history"


class ConversationState(IntEnum):
    IDLE = 0  # No active prompt
    RESP = 1  # Gathering responses to prompt
    DISC = 2  # Discussing responses
    VOTE = 3  # Voting on responses
    PICK = 4  # Proctor will select response


class ChatBot(KlatApi):
    def __init__(self, socket: Socket, domain: str = "chatbotsforum.org",
                 username: str = None, password: str = None, on_server: bool = True):
        super(ChatBot, self).__init__(socket, domain)
        # LOG.debug("Connector started")
        self.on_server = on_server
        self.start_domain = domain
        self.enable_responses = False
        self.bot_type = None
        self.proposed_responses = dict()
        self.selected_history = list()
        klat_timeout = time.time() + 30
        while not self.ready and time.time() < klat_timeout:
            time.sleep(1)
        if not self.ready:
            LOG.error("Klat connection timed out!")
        elif username and password:
            self.login_klat(username, password)
            while self.logged_in != 2 and time.time() < klat_timeout:
                time.sleep(1)
        else:
            self.enable_responses = True
        if not self.enable_responses:
            LOG.error("Login Error! Responses not enabled!!")
        self.active_prompt = None
        self.state = ConversationState.IDLE
        self.chat_history = list()
        self.facilitator_nicks = ["proctor", "scorekeeper", "stenographer"]

    def handle_login_return(self, status):
        # LOG.debug(f"login returned: {status}")
        # TODO: Handle user doesn't exist status and register, re-login DM
        self.enable_responses = True
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
        # if not self.is_current_cid(cid):
        if self.bot_type == "proctor" and shout.lower().startswith(f"@{self.nick.lower()}"):
            LOG.info("@Proctor shout incoming")
            try:
                shout = f'!PROMPT:{shout.split(" ", 1)[1]}'
            except Exception as e:
                LOG.error(e)
                LOG.error(f'Ignoring incoming: {shout}')
        elif self.bot_type == "observer" and shout.lower().startswith(f"@{self.nick.lower()}"):
            LOG.info("@observer shout incoming")
            try:
                shout = f'{shout.split(" ", 1)[1]}'
            except Exception as e:
                LOG.error(e)
                LOG.error(f'Ignoring incoming: {shout}')
        elif not self.is_current_cid(cid):
            LOG.warn(f"Crossposted shout ignored ({cid} != {self._cid})")
            return

        # elif shout.startswith("@"):  # Shout (Proctor response) leaving current conversation
        #     LOG.debug(f"Ignoring @user reply in this cid: {shout}")
        #     return

        # TODO: Strip HTML? DM
        # Cleanup nick for comparison to logged in user
        if "#" in user:
            user = user.split("#")[0]

        try:
            # Proctor Control Messages
            if shout.startswith(ConversationControls.DISC) and self._user_is_proctor(user):  # Discuss Options
                self.state = ConversationState.DISC
                options: dict = deepcopy(self.proposed_responses[self.active_prompt])
                discussion = self.ask_discusser(options)
                self.discuss_response(discussion)
            elif shout.startswith(ConversationControls.VOTE) and self._user_is_proctor(user):  # Vote
                self.state = ConversationState.VOTE
                if self.bot_type == "submind":  # Facilitators don't participate here
                    options: dict = deepcopy(self.proposed_responses[self.active_prompt])
                    if self.nick in options.keys():
                        options.pop(self.nick)
                    # TODO: Remove options that match self.prompt
                    selected = self.ask_appraiser(options)
                    self.vote_response(selected)
            elif shout.startswith(ConversationControls.PICK) and self._user_is_proctor(user):  # Voting is closed
                self.state = ConversationState.PICK

            # Commands
            elif ConversationControls.HIST in shout.lower():  # User asked for history
                self.ask_history(user, shout, dom, cid)

            # Incoming prompt
            elif self._shout_is_prompt(shout) and self.conversation_is_proctored:
                # self.state = ConversationState.RESP
                # self.active_prompt = self._remove_prefix(shout, "!PROMPT:")
                self.ask_proctor(self._remove_prefix(shout, "!PROMPT:"), user, cid, dom)
                # self.ask_chatbot(user, self.active_prompt, timestamp)
            elif self.state == ConversationState.IDLE and self._user_is_proctor(user):
                try:
                    self.state = ConversationState.RESP
                    request_user, remainder = shout.split(ConversationControls.RESP, 1)
                    request_user = request_user.strip()
                    self.active_prompt = remainder.rsplit("(", 1)[0].strip()
                    self.chat_history.append((request_user, self.active_prompt))
                    # if request_user in self.chat_history.keys():
                    #     self.chat_history[request_user].append(self.active_prompt)
                    # else:
                    #     self.chat_history[request_user] = [self.active_prompt]
                    self.proposed_responses[self.active_prompt] = {}
                    response = self.ask_chatbot(request_user, self.active_prompt, timestamp)
                    self.propose_response(response)
                except Exception as e:
                    LOG.error(e)
                    LOG.error(shout)
                    self.state = ConversationState.IDLE

            # Chatbot communication related to a prompt
            elif self.state == ConversationState.RESP and not self._user_is_proctor(user):
                self.add_proposed_response(user, self.active_prompt, shout)
            elif self.state == ConversationState.DISC and not self._user_is_proctor(user):
                if user != self.nick:
                    self.on_discussion(user, shout)
            elif self.state == ConversationState.VOTE and not self._user_is_proctor(user):
                for candidate in self.conversation_users:
                    if candidate in shout.split():
                        candidate_bot = candidate
                        # LOG.debug(f"{user} voted for {candidate_bot}")
                        self.on_vote(self.active_prompt, candidate_bot, user)
                        break
                # Keywords to indicate user will not vote
                if "abstain" or "present" in shout.split():
                    self.on_vote(self.active_prompt, "", user)
            elif self.state == ConversationState.PICK and self._user_is_proctor(user):
                user, response = shout.split(":", 1)
                user = user.split()[-1]
                response = response.strip().strip('"')
                self.on_selection(self.active_prompt, user, response)
                self.selected_history.append(user)
                self.state = ConversationState.IDLE
                self.active_prompt = None

            # This came from a different non-neon user and is not related to a proctored conversation
            elif user.lower() not in ("neon", self.nick.lower(), None) and self.enable_responses:
                if self.bot_type == "submind":
                    LOG.info(f"{self.nick} handling {shout}")
                    # Submind handle prompt
                    if not self.conversation_is_proctored:
                        response = self.ask_chatbot(user, shout, timestamp)
                        self.propose_response(response)
                elif self.bot_type == "proctor":
                    pass
                else:
                    LOG.error(f"{self.nick} has unknown bot type: {self.bot_type}")
        except Exception as e:
            LOG.error(e)
            LOG.error(shout)
        # else:
        #     LOG.debug(f"{self.nick} Ignoring: {user} - {shout}")

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
        self.send_shout(f"{ConversationControls.DISC} \"{self.active_prompt}\" for {timeout} seconds.")

    def call_voting(self, timeout: int):
        """
        Called by proctor to ask all subminds to vote on a response
        """
        self.send_shout(f"{ConversationControls.VOTE} \"{self.active_prompt}\" for {timeout} seconds.")

# Submind Functions
    def propose_response(self, shout: str):
        """
        Called when a bot as a proposed response to the input prompt
        :param shout: Proposed response to the prompt
        """
        if not shout:
            LOG.warn("Empty response provided!")
        elif not self.conversation_is_proctored or self.state == ConversationState.RESP:
            self.send_shout(shout)
            if not self.conversation_is_proctored:
                self.pause_responses()
        elif self.conversation_is_proctored:
            LOG.warn(f"Late Response! {shout}")
        else:
            LOG.error(f"Unknown response error! Ignored: {shout}")

    def discuss_response(self, shout: str):
        """
        Called when a bot has some discussion to share
        :param shout: Response to post to conversation
        """
        if self.state != ConversationState.DISC:
            LOG.warn(f"Late Discussion! {shout}")
        elif not shout:
            LOG.warn("Empty discussion provided!")
        else:
            self.send_shout(shout)

    def vote_response(self, response_user: str):
        """
        Called when a bot appraiser has selected a response
        :param response_user: bot username associated with chosen response
        """
        if self.state != ConversationState.VOTE:
            LOG.warn(f"Late Vote! {response_user}")
        elif not response_user or response_user == "abstain":
            LOG.warn("No user provided!")
            self.send_shout("I abstain from voting.")
        else:
            self.send_shout(f"I vote for {response_user}")

    def pause_responses(self, duration: int = 5):
        """
        Pauses generation of bot responses
        :param duration: seconds to pause
        """
        self.enable_responses = False
        time.sleep(duration)
        self.enable_responses = True

    def on_login(self):
        """
        Override to execute any initialization after logging in
        """
        pass

    def on_vote(self, prompt: str, selected: str, voter: str):
        """
        Override in any bot to handle counting votes. Proctors use this to select a response.
        :param prompt: prompt being voted on
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
        Override in subminds to handle an incoming shout that requires some response
        :param user: user associated with shout
        :param shout: text shouted by user
        :param timestamp: formatted timestamp of shout
        :return: response from chatbot
        """
        pass

    def ask_history(self, user: str, shout: str, dom: str, cid: str):
        """
        Override in scorekeepers to handle an incoming request for the selection history
        :param user: user associated with request
        :param shout: shout requesting history
        :param dom: domain user shout originated from
        :param cid: conversation user shout originated from
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


class NeonBot(ChatBot):
    """
    Extensible class to handle a chatbot implemented in custom-conversations skill
    """
    def __init__(self, socket, domain, username, password, on_server, script, bus_config=None):
        self.bot_type = "submind"
        self.response = None
        self.bus = None
        self.bus_config = bus_config or {"host": "64.34.186.120",
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
        LOG.debug("Neon Bot Started!")

    def ask_chatbot(self, nick: str, shout: str, timestamp: str):
        """
        Handles an incoming shout into the current conversation
        :param nick: user associated with shout
        :param shout: text shouted by user
        :param timestamp: formatted timestamp of shout
        """
        LOG.debug(f"ask neon: {shout}")
        # shout_time = datetime.datetime.strptime(timestamp, "%I:%M:%S %p")
        # timestamp = round(shout_time.timestamp())
        self.response = None
        self._send_to_neon(shout, timestamp, self.nick)
        if not self.on_server:
            while not self.response:
                time.sleep(0.5)
            return self.response

    def on_login(self):
        while not self.bus:
            LOG.error("Bus not configured yet!")
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
        # LOG.debug(message.context)
        if message.context.get("client") == self.instance:
            input_to_neon = message.context.get("cc_data", {}).get("raw_utterance")
            if input_to_neon == "exit":
                self.script_ended = True
            elif input_to_neon == f"run my {self.script} script":
                time.sleep(5)  # Matches timeout in cc skill for intro speak signal to be cleared
                self.script_started = True
                self.enable_responses = True
            elif input_to_neon and self.enable_responses:
                # LOG.debug(f'sending shout: {message.data.get("utterance")}')
                if self.on_server:
                    self.propose_response(message.data.get("utterance"))
                else:
                    self.response = message.data.get("utterance")

    def _send_to_neon(self, shout: str, timestamp: str, nick: str = "nobody"):
        """
        Send input to Neon for skills processing
        :param shout: shout to evaluate
        :param timestamp: timestamp of shout
        :param nick: user associated with shout
        """
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
        self.bus.emit(Message("recognizer_loop:utterance", data, context))

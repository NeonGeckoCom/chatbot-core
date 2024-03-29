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
from enum import IntEnum

from engineio.socket import Socket
# import threading
from threading import Thread, Event

from klat_connector.klat_api import KlatApi
from klat_connector import start_socket
from chatbot_core.utils import init_message_bus
from chatbot_core.logger import make_logger
from mycroft_bus_client import Message, MessageBusClient
from autocorrect import Speller
from nltk.translate.bleu_score import sentence_bleu
from nltk import word_tokenize
import jellyfish
import spacy

LOG = make_logger("chatbot")


def find_closest_answer(algorithm: str = 'random', sentence: str = None, options: dict = None):
    """
        Handles an incoming shout into the current conversation
        :param algorithm: algorithm considered
        :param sentence: base sentence
        :param options: options to pick best one from
    """
    if not sentence:
        LOG.warning('Empty sentence supplied')
        return sentence
    if not options or len(options.keys()) == 0:
        LOG.warning('No options provided')
        return sentence
    if algorithm == 'random':
        closest_answer = random.choice(options)
    elif algorithm == 'bleu_score':
        bleu_scores = []
        response_tokenized = word_tokenize(sentence.lower())
        for option in options.keys():
            opinion_tokenized = word_tokenize(options[option].lower())
            if len(opinion_tokenized) > 0:
                if min(len(response_tokenized), len(opinion_tokenized)) < 4:
                    weighting = 1.0 / min(len(response_tokenized), len(opinion_tokenized))
                    weights = tuple([weighting] * min(len(response_tokenized), len(opinion_tokenized)))
                else:
                    weights = (0.25, 0.25, 0.25, 0.25)
                bleu_scores.append(
                    (option, sentence_bleu([response_tokenized], opinion_tokenized, weights=weights)))
        max_score = max([x[1] for x in bleu_scores]) if len(bleu_scores) > 0 else 0
        closest_answer = random.choice(list(filter(lambda x: x[1] == max_score, bleu_scores)))[0]
        LOG.info(f'Closest answer is {closest_answer}')
    elif algorithm == 'damerau_levenshtein_distance':
        closest_distance = None
        closest_answer = None
        try:
            for option in options.items():
                distance = jellyfish.damerau_levenshtein_distance(option[1], sentence)
                if not closest_distance or closest_distance > distance:
                    closest_distance = distance
                    closest_answer = option[0]
            LOG.info(f'Closest answer is {closest_answer}')
        except Exception as e:
            LOG.error(e)
    else:
        LOG.error(f'Unknown algorithm supplied:{algorithm}')
        return sentence
    return closest_answer


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


class ChatBot(KlatApi):
    def __init__(self, socket: Socket, domain: str = "chatbotsforum.org",
                 username: str = None, password: str = None, on_server: bool = True, is_prompter: bool = False):
        socket = socket or start_socket()
        init_nick = "Prompter" if is_prompter else ""
        super(ChatBot, self).__init__(socket, domain, init_nick)
        global LOG
        # self.log.debug("Connector started")
        self.on_server = on_server
        self.is_prompter = is_prompter
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

    def handle_login_return(self, status):
        # self.log.debug(f"login returned: {status}")

        if status == 888:
            self.enable_responses = False
            LOG.info(f"New user, registering {self.username}")
            self.register_klat(self.username, self.password)
        elif status == 999:
            LOG.error(f"Incorrect Password!")
        elif status == 777:
            LOG.error(f"User already logged in and was logged out!")
        elif status == 666:
            LOG.error(f"Nickname in use")
        elif status == 555:
            LOG.error("Old nick not found!")
        elif status != 0:
            LOG.error(f"Unknown error {status} occurred while logging in!")
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

            if self.bot_type == "proctor":
                self.log.info("@Proctor shout incoming")
                try:
                    self.ask_proctor(shout, user, cid, dom)
                except Exception as e:
                    self.log.error(e)
                    self.log.error(f'Ignoring incoming: {shout}')
            elif self.bot_type == "observer":
                self.log.info("@observer shout incoming")
                # TODO: Consider something here DM
                # try:
                #     shout = f'{shout.split(" ", 1)[1]}'
                # except Exception as e:
                #     self.log.error(e)
                #     self.log.error(f'Ignoring incoming: {shout}')
            elif self.bot_type == "submind":
                self.log.info(f"@bot shout incoming")
                resp = self.at_chatbot(user, shout, timestamp)
                if self.is_prompter:
                    self.log.info(f"Prompter bot got reply: {shout}")
                    # private_cid = self.get_private_conversation([user])
                    self.send_shout(resp)
                    return
        # Ignore anything from a different conversation that isn't @ this bot
        elif not self.is_current_cid(cid):
            if self.bot_type == "proctor" and self._user_is_prompter(user):
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
        elif not self._user_is_proctor(user) and user.lower() in self.facilitator_nicks and self.bot_type == "submind":
            self.log.debug(f"{self.nick} ignoring facilitator shout: {shout}")
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
                participants = shout[:-len(ConversationControls.WAIT)]
                participants = set(participant.lower().strip() for participant in participants.split(","))
                self.participant_history.append(participants)

                if self.bot_type == "submind" and self.nick.lower() not in re.split("[, ]", shout.lower()):
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
                        if self.bot_type == "proctor":
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
            self.proposed_responses[prompt][user.lower()] = response
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
        return nick.lower() == "proctor"

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


class NeonBot(ChatBot):
    """
    Extensible class to handle a chatbot implemented in custom-conversations skill
    """

    def __init__(self, socket, domain, username, password, on_server, script, is_prompter=False, bus_config=None):
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
        super(NeonBot, self).__init__(socket, domain, username, password, on_server, is_prompter)

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
        # self.bus = MessageBusClient(self.bus_config["host"], self.bus_config["port"],
        #                             self.bus_config["route"], self.bus_config["ssl"])
        # t = Thread(target=self.bus.run_forever)
        # t.daemon = True
        # t.start()
        t, self.bus = init_message_bus(self.bus_config)
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
                   "client": "api",
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


class ParlaiBot(ChatBot):

    def __init__(self, socket, domain, username, password, on_server, interactive_script, response_timeout=25,
                 is_prompter=False):
        """
        Instantiate a ParlAI-specific chatbot
        :param socket: a socketIO connection instance (requires to specify server and port).
                                        Use klat_connector.start_socket to instanciate one
        :param domain: starting domain
        :param username: klat username
        :param password: klat user password
        :param on_server: True if bot is being run on server, False if locally
        :param interactive_script: a script that creates a world within the ParlAI framework (for reference, see any
                                        ParlaiBot-extended class in the chatbots package, e.g. TuckerBot)
        :param response_timeout: timeout in seconds for ParlAI world to generate a response for a prompt
        :param is_prompter: True if bot is to generate prompts for the Proctor
        """
        super(ParlaiBot, self).__init__(socket, domain, username, password, on_server, is_prompter)

        self.on_server = on_server
        self.bot_type = "submind"
        self.nlp_engine = spacy.load("en_core_web_sm")

        self.agent_id = 'local_agent'
        self.event = Event()
        self.parlai_thread = Thread(target=interactive_script, args=(self,), daemon=True)
        self.parlai_thread.start()

        self.current_response = ''
        self.current_shout = ''
        self.finished = False

        self._response_timeout = response_timeout

    # Agent-specific methods
    def observe(self, msg):
        """
        Observe the other bot's action result
        """
        if msg['id'] != 'context':
            self.event.set()
            self.current_response = msg["text"]
        self.log.debug(f'[OUT]: {self.current_response}')

    def act(self):
        """
        Make an action to provide the other agent in the task with an input
        """
        reply = self._construct_reply()
        # save the current shout locally and clear the attribute to prevent parley() without incoming shout
        reply_text = self.current_shout
        self.current_shout = ''
        self.log.debug(f'CURRENT SHOUT {reply_text}')
        # check for episode done
        if '[DONE]' in reply_text:
            raise StopIteration
        # set reply text
        reply['text'] = reply_text
        # check if finished
        if '[EXIT]' in reply_text:
            self.finished = True
            raise StopIteration
        return reply

    # Compatibility methods
    def getID(self):
        """
        Return agent_id of the bot as an agent for ParlAI
        """
        return self.agent_id

    def epoch_done(self):
        """
        Informs DD that the epoch is done. Using for exiting the process.
        """
        return self.finished

    def reset(self):
        """
        Required for defining by agent, e.g. for clearing local variables on exit
        """
        pass

    # Helper methods
    @staticmethod
    def _capitalize(resp: str) -> str:
        """
        Capitalize each sentence, and all "I"s if a pronoun.
        :param resp: a response to be capitalized
        :return: capitalized string
        """
        cap_marks = (".", "!", "?")
        needs_cap = True  # the first word should be capitalized as well
        cap_resp = []
        for word in resp.split():
            if needs_cap:
                cap_resp.append(word.capitalize())
                needs_cap = False
            elif word in cap_marks or any([word.endswith(mark) for mark in cap_marks]):
                cap_resp.append(word)
                needs_cap = True
            elif word == "i":
                cap_resp.append("I")
                needs_cap = False
            else:
                cap_resp.append(word)
        return " ".join(cap_resp)

    @staticmethod
    def _fix_spacing(resp: str) -> str:
        """Fix spacing, e.g. no spaces before the full period '.', or before and after an apostrophe.
        :param resp: a phrase to fix"""
        fixed_resp = ''
        for i in range(len(resp)):
            try:
                if resp[i] == " " and resp[i + 1] in (".", "?", "!", "'"):
                    continue
                if resp[i] == " " and resp[i - 1] == "'" and resp[i - 2] != "s":
                    continue
                else:
                    fixed_resp = fixed_resp + resp[i]
            except IndexError:
                continue
        return fixed_resp

    # Abstract helper methods
    @abstractmethod
    def _construct_reply(self):
        """
        Construct a reply using parlai.core.message.Message in a concrete class. This method is a hack around
        ParlAI installation, so this MUST always be defined in child classes
        """
        raise NotImplementedError

    @abstractmethod
    def _lookup_cache(self, key):
        """
        Lookup cache for particular prompt:response pair
        """
        pass

    @abstractmethod
    def _update_cache(self, prompt: str, resp: str) -> None:
        """
        Save the current prompt and resp to cache
        :param prompt: incoming prompt
        :param resp: generated response for prompt
        :return:
        """
        pass

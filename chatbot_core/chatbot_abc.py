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

from abc import ABC, abstractmethod
from queue import Queue
from typing import Optional

from chatbot_core.utils import *

LOG = make_logger("chatbot")


class ChatBotABC(ABC):
    """Abstract class gathering all the chatbot-related methods children should implement"""

    def __init__(self):
        self.shout_queue = Queue(maxsize=256)
        self.__log = None

    @property
    def log(self):
        if not self.__log:
            global LOG
            self.__log = make_logger(self.__class__.__name__)
            self.__log.setLevel(LOG.level)
            LOG = self.__log
        return self.__log

    @abstractmethod
    def parse_init(self, *args, **kwargs) -> tuple:
        """Parses dynamic init arguments on the considered instance class initialization"""
        pass

    @abstractmethod
    def on_vote(self, prompt_id: str, selected: str, voter: str):
        """
        Override in any bot to handle counting votes. Proctors use this to select a response.
        :param prompt_id: id of prompt being voted on
        :param selected: bot username voted for
        :param voter: user who voted
        """
        pass

    @abstractmethod
    def on_discussion(self, user: str, shout: str):
        """
        Override in any bot to handle discussion from other subminds. This may inform voting for the current prompt
        :param user: user associated with shout
        :param shout: shout to be considered
        """
        pass

    @abstractmethod
    def on_proposed_response(self):
        """
        Override in Proctor to check when to notify bots to vote
        """
        pass

    @abstractmethod
    def on_selection(self, prompt: str, user: str, response: str):
        """
        Override in any bot to handle a proctor selection of a response
        :param prompt: input prompt being considered
        :param user: user who proposed selected response
        :param response: selected response to prompt
        """
        pass

    @abstractmethod
    def on_ready_for_next(self, user: str):
        """
        Notifies when a bot is finished handling the current prompt and is ready for the next one. This should happen
        shortly after the proctor selects a response.
        :param user: user who is ready for the next prompt
        """
        pass

    @abstractmethod
    def at_chatbot(self, user: str, shout: str, timestamp: str) -> str:
        """
        Override in subminds to handle an incoming shout that is directed at this bot. Defaults to ask_chatbot.
        :param user: user associated with shout
        :param shout: text shouted by user
        :param timestamp: formatted timestamp of shout
        :return: response from chatbot
        """
        return self.ask_chatbot(user, shout, timestamp)

    @abstractmethod
    def ask_proctor(self, prompt: str, user: str, cid: str, dom: str):
        """
        Override in proctor to handle a new prompt to queue
        :param prompt: Cleaned prompt for discussion
        :param user: user associated with prompt
        :param cid: cid prompt is from
        :param dom: dom prompt is from
        """
        pass

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
    def ask_appraiser(self, options: dict) -> str:
        """
        Override in bot to handle selecting a response to the given prompt. Vote is for the name of the best responder.
        :param options: proposed responses (botname: response)
        :return: user selected from options or "abstain" for no vote
        """
        pass

    @abstractmethod
    def ask_discusser(self, options: dict) -> str:
        """
        Override in bot to handle discussing options for the given prompt. Discussion can be anything.
        :param options: proposed responses (botname: response)
        :return: Discussion response for the current prompt
        """
        pass

    @staticmethod
    def _shout_is_prompt(shout):
        """
        Determines if the passed shout is a new prompt for the proctor.
        :param shout: incoming shout
        :return: true if shout should be considered a prompt
        """
        return shout.lower().startswith("!prompt:")

    @staticmethod
    def _hesitate_before_response(start_time, timeout: int = 5):
        """
            Applies some hesitation time before response

            :param start_time: initial time
            :param timeout: hesitation timeout
        """
        if time.time() - start_time < timeout:
            # Apply some random wait time if we got a response very quickly
            time.sleep(random.randrange(0, 50) / 10)
        else:
            LOG.debug("Skipping artificial wait!")

    @abstractmethod
    def _send_first_prompt(self):
        """
            Sends an initial prompt to the proctor for a prompter bot
        """
        pass

    @abstractmethod
    def handle_shout(self, *args, **kwargs):
        """
            Handles an incoming shout into the current conversation
            :param user: user associated with shout
            :param shout: text shouted by user
            :param cid: cid shout belongs to
            :param dom: domain conversation belongs to
            :param timestamp: formatted timestamp of shout
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
        return "prompter" in nick.lower()

    @abstractmethod
    def vote_response(self, response_user: str, cid: Optional[str] = None):
        """
            Called when a bot appraiser has selected a response
            :param response_user: bot username associated with chosen response
            :param cid: dedicated conversation id (optional)
        """
        pass

    @abstractmethod
    def _handle_next_shout(self):
        """
        Called recursively to handle incoming shouts synchronously
        """
        pass

    @abstractmethod
    def _pause_responses(self, duration: int = 5):
        """
            Pauses generation of bot responses

            :param duration: seconds to pause
        """
        pass

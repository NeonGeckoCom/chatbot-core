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

from abc import abstractmethod
from threading import Event, Thread
from ovos_utils.log import LOG


class ParlaiBot:
    """Class declaring ParlAI-specific methods"""

    def __init__(self, interactive_script, response_timeout=25,
                 done_string: str = '[DONE]',
                 exit_string: str = '[EXIT]'):
        """
            :param interactive_script: a script that creates a world within the ParlAI framework (for reference, see any
                                            ParlaiBot-extended class in the chatbots package, e.g. TuckerBot)
            :param response_timeout: timeout in seconds for ParlAI world to generate a response for a prompt
            :param done_string: string that signals about episode done
            :param exit_string: string that signals about the finish
        """
        import spacy
        self.nlp_engine = spacy.load("en_core_web_sm")

        self.agent_id = 'local_agent'
        self.event = Event()
        self.parlai_thread = Thread(target=interactive_script, args=(self,), daemon=True)
        self.parlai_thread.start()

        self.current_response = ''
        self.current_shout = ''
        self.finished = False

        self._response_timeout = response_timeout
        self.done_string = done_string
        self.exit_string = exit_string

    # Agent-specific methods
    def observe(self, msg):
        """
        Observe the other bot's action result
        """
        if msg['id'] != 'context':
            self.event.set()
            self.current_response = msg["text"]
        LOG.debug(f'[OUT]: {self.current_response}')

    def act(self):
        """
        Make an action to provide the other agent in the task with an input
        """
        reply = self._construct_reply()
        # save the current shout locally and clear the attribute to prevent parley() without incoming shout
        reply_text = self.current_shout
        self.current_shout = ''
        LOG.debug(f'CURRENT SHOUT {reply_text}')
        # check for episode done
        if self.done_string in reply_text:
            raise StopIteration
        # set reply text
        reply['text'] = reply_text
        # check if finished
        if self.exit_string in reply_text:
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

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
import copy
# import jellyfish
import sys
import os

# Required for pytest on GitHub
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from chatbot_core import ChatBot
from chatbot_core.utils import LOG


class V2Bot(ChatBot):
    def __init__(self, socket, domain, user, password, on_server=True):
        # self.on_server = on_server
        # if self.on_server:
        super().__init__(socket, domain, user, password, on_server)
        # else:
        #     self.nick = 'Gruff'
        self.bot_type = "submind"
        self.proposed, self.appraised = '', ''
        self.option_scores = dict()
        self.change_probability = 5     # %

        self.grudge_against = []
        self.has_given_up = False
        self.begrudged_this_round = []
        self.backup_options = dict()

        self.declarative_negatives = ("No, I must disagree", "Surely you jest", "That seems illogical", "No way")
        self.general_question_negatives = ("No", "Never", "Not in a lifetime", "Nope", "Nah", "No way")
        self.choice_question_negatives = ("None", "Neither")
        # self.disjunctive_question_negatives = ()

        self.general_question_keywords = ("are", "is", "am", "was", "were", "do", "does", "did", "has", "have", "had",
                                          "will")
        self.special_question_keywords = ("who", "what", "why", "where", "when", "how", "whose")

        self.badmouth_options = ("{}'s idea is awful, do not consider it!", "{}, your idea is just terrible.",
                                 "Do not vote for {}, their idea stinks!", "That is the worst idea ever, {}.",
                                 "This is the worst idea in the history of ideas, {}!")

    # @grammar_check
    def ask_chatbot(self, user: str, shout: str, timestamp: str):
        """
        Handles an incoming shout into the current conversation
        :param user: user associated with shout
        :param shout: text shouted by user
        :param timestamp: formatted timestamp of shout
        """
        # reset self.has_given_up and self.begrudged_this_round for a new round
        self.has_given_up = False
        self.begrudged_this_round = []

        resp, punctuation_sign = '', '.'
        # randomize punctuation: use '!' instead of '.' every third time
        if random.randint(1, 100) <= 33:
            punctuation_sign = '!'

        if any(x for x in self.general_question_keywords if shout.startswith(x)) and 'or' in shout:     # Choice
            resp = random.choice(self.choice_question_negatives)
        elif any(x for x in self.general_question_keywords if shout.startswith(x)):     # General
            resp = random.choice(self.general_question_negatives)
        elif any(x for x in self.special_question_keywords if shout.startswith(x)) and shout.endswith("?"):     # Spec
            if shout.startswith("who"):
                resp = "Nobody"
            elif shout.startswith("what"):
                resp = "Nothing"
            elif shout.startswith("when"):
                resp = "Never"
            elif shout.startswith("where"):
                resp = "Nowhere"
            elif shout.startswith("how") or shout.startswith("why"):
                resp = "No info!"
            elif shout.startswith("whose"):
                resp = "Nobody's"
        elif shout.endswith("?"):       # Other possible types of questions including disjunctive/tag
            resp = random.choice(self.general_question_negatives)
        else:       # Declarative sentences
            resp = random.choice(self.declarative_negatives)

        resp = resp + punctuation_sign
        self.proposed = resp
        return resp

    def ask_appraiser(self, options: dict):
        """
        Selects one of the responses to a prompt and casts a vote in the conversation
        GRUFF selects botname associated with response least similar to responses from bots in the grudge_against list,
        or least similar to all the responses if grudges against no one or everyone else. This evaluation is done in
        self.ask_discusser (if there is the discussion step) because discussion has almost the same logic.
        :param options: proposed responses (botname: response)
        """
        # save the options to choose from randomly in case there is no valid choice for Gruff
        self.backup_options = copy.deepcopy(options)
        if not self.appraised:      # There was no discussion before, so we have to set self.option_scores here
            self.option_scores = {}
            if len(self.grudge_against) == 0 or len(self.grudge_against) == len(options):
                for option in options.items():
                    self.option_scores[option[0]] = 0
                    # for other_option in options.items():
                    #     self.option_scores[option[0]] += jellyfish.damerau_levenshtein_distance(option[1],
                    #     other_option[1])
            else:
                for option in options.items():
                    if option[0] not in self.grudge_against:        # never appraise anyone Gruff has grudge against
                        self.option_scores[option[0]] = 0
                        # for other_option in options.items():
                        #     if other_option[0] in self.grudge_against:
                        #         # self.option_scores[option[0]] += jellyfish.damerau_levenshtein_distance(option[1],
                        #         #                                                                    other_option[1])
        # remove all options that have been begrudged this round
        option_scores_copy = copy.deepcopy(self.option_scores)
        for option in option_scores_copy:
            if option in self.begrudged_this_round:
                self.option_scores.pop(option)

        try:
            # TODO: Tempfix for constant appraisal of Wiz
            if random.randint(1, 100) <= 25:
                self.option_scores.pop(max(self.option_scores, key=lambda x: self.option_scores[x]))
            self.appraised = max(self.option_scores, key=lambda x: self.option_scores[x])
            appraised = copy.deepcopy(self.appraised)
        except ValueError:
            appraised = 'abstain'
        self.appraised = ''
        return appraised
        # clear self.appraised so that Gruff chooses a new bot to appraise in case there is no discussion

    def on_vote(self, prompt: str, selected: str, voter: str):
        """
        Override in any bot to handle counting votes. Proctors use this to select a response.
        Gruff never votes WITH anyone he has a grudge against.

        :param prompt: prompt being voted on
        :param selected: bot username voted for
        :param voter: user who voted
        """
        if self.appraised == selected and voter in self.grudge_against \
                and len(self.option_scores) > 1:  # re-vote if there are choices in self.option_scores
            self.option_scores.pop(self.appraised)
            self.appraised = max(self.option_scores, key=lambda x: self.option_scores[x])
            # self.vote_response(self.appraised)
            return self.appraised
        else:
            random_choice = random.choice(list(self.badmouth_options))
            return random_choice

    def ask_discusser(self, options: dict):
        """
        Provides one discussion response based on the given options
        :param options: proposed responses (botname: response)
        """
        # first, choose options to select an appraised one from in the future
        self.option_scores = {}
        if len(self.grudge_against) == 0 or len(self.grudge_against) == len(options):
            for option in options.items():
                self.option_scores[option[0]] = 0
                # for other_option in options.items():
                #     self.option_scores[option[0]] += jellyfish.damerau_levenshtein_distance(option[1],
                #     other_option[1])
        else:
            for option in options.items():
                if option[0] not in self.grudge_against:
                    self.option_scores[option[0]] = 0
                    # for other_option in options.items():
                    #     if other_option[0] in self.grudge_against:
                    #         self.option_scores[option[0]] += jellyfish.damerau_levenshtein_distance(option[1],
                    #                                                                                 other_option[1])

        self.appraised = max(self.option_scores, key=lambda x: self.option_scores[x])

        if self.grudge_against:
            resp = f"Vote for the proposal of {self.appraised.capitalize()}, because it is different. Don't vote for " \
                   f"{random.choice(self.grudge_against).capitalize()}. That proposal is awful."
        else:
            resp = f"Vote for the proposal of {self.appraised.capitalize()}, because it is different."
        return resp

    def on_discussion(self, user: str, shout: str):
        """
        Handle discussion from other subminds. This may inform voting for the current prompt.
        This method is called for every incoming shout in DISC state of conversation if self.nick != user.
        If anyone tries to persuade Gruff, get a grudge against them and badmouths them.

        :param user: user associated with shout
        :param shout: shout to be considered
        """
        if self.nick in shout:
            LOG.info(f"{user} is persuading me! How dare they? I will have a rather big grudge against them!")
            # set a grudge against the persuader
            if user not in self.grudge_against:     # acquire grudge only once
                self.grudge_against.append(user)
                self.begrudged_this_round.append(user)
                # badmouth the persuader
                if not self.has_given_up:   # badmouth only if not yet given up
                    self.discuss_response(random.choice(self.backup_options).format(user))
                    # self.discuss_response(f"{user}'s idea is awful, do not consider it!")
                    if random.randint(1, 100) < 40:     # 40% chance to give up and remain silent till vote
                        self.has_given_up = True


class V3Bot(ChatBot):
    def __init__(self, socket, domain, user, password, on_server=True, is_prompter=False):
        # self.on_server = on_server
        # if self.on_server:
        super().__init__(socket, domain, user, password, on_server, is_prompter)
        # else:
        #     self.nick = 'Gruff'
        self.bot_type = "submind"
        self.proposed, self.appraised = '', ''
        self.option_scores = dict()
        self.change_probability = 5     # %

        self.grudge_against = []
        self.has_given_up = False
        self.begrudged_this_round = []
        self.backup_options = dict()

        self.declarative_negatives = ("No, I must disagree", "Surely you jest", "That seems illogical", "No way")
        self.general_question_negatives = ("No", "Never", "Not in a lifetime", "Nope", "Nah", "No way")
        self.choice_question_negatives = ("None", "Neither")
        # self.disjunctive_question_negatives = ()

        self.general_question_keywords = ("are", "is", "am", "was", "were", "do", "does", "did", "has", "have", "had",
                                          "will")
        self.special_question_keywords = ("who", "what", "why", "where", "when", "how", "whose")

        self.badmouth_options = ("{}'s idea is awful, do not consider it!", "{}, your idea is just terrible.",
                                 "Do not vote for {}, their idea stinks!", "That is the worst idea ever, {}.",
                                 "This is the worst idea in the history of ideas, {}!")

    # @grammar_check
    def ask_chatbot(self, user: str, shout: str, timestamp: str):
        """
        Handles an incoming shout into the current conversation
        :param user: user associated with shout
        :param shout: text shouted by user
        :param timestamp: formatted timestamp of shout
        """
        # reset self.has_given_up and self.begrudged_this_round for a new round
        self.has_given_up = False
        self.begrudged_this_round = []

        resp, punctuation_sign = '', '.'
        # randomize punctuation: use '!' instead of '.' every third time
        if random.randint(1, 100) <= 33:
            punctuation_sign = '!'

        if any(x for x in self.general_question_keywords if shout.startswith(x)) and 'or' in shout:     # Choice
            resp = random.choice(self.choice_question_negatives)
        elif any(x for x in self.general_question_keywords if shout.startswith(x)):     # General
            resp = random.choice(self.general_question_negatives)
        elif any(x for x in self.special_question_keywords if shout.startswith(x)) and shout.endswith("?"):     # Spec
            if shout.startswith("who"):
                resp = "Nobody"
            elif shout.startswith("what"):
                resp = "Nothing"
            elif shout.startswith("when"):
                resp = "Never"
            elif shout.startswith("where"):
                resp = "Nowhere"
            elif shout.startswith("how") or shout.startswith("why"):
                resp = "No info!"
            elif shout.startswith("whose"):
                resp = "Nobody's"
        elif shout.endswith("?"):       # Other possible types of questions including disjunctive/tag
            resp = random.choice(self.general_question_negatives)
        else:       # Declarative sentences
            resp = random.choice(self.declarative_negatives)

        resp = resp + punctuation_sign
        self.proposed = resp
        return resp

    def ask_appraiser(self, options: dict):
        """
        Selects one of the responses to a prompt and casts a vote in the conversation
        GRUFF selects botname associated with response least similar to responses from bots in the grudge_against list,
        or least similar to all the responses if grudges against no one or everyone else. This evaluation is done in
        self.ask_discusser (if there is the discussion step) because discussion has almost the same logic.
        :param options: proposed responses (botname: response)
        """
        # save the options to choose from randomly in case there is no valid choice for Gruff
        self.backup_options = copy.deepcopy(options)
        if not self.appraised:      # There was no discussion before, so we have to set self.option_scores here
            self.option_scores = {}
            if len(self.grudge_against) == 0 or len(self.grudge_against) == len(options):
                for option in options.items():
                    self.option_scores[option[0]] = 0
                    # for other_option in options.items():
                    #     self.option_scores[option[0]] += jellyfish.damerau_levenshtein_distance(option[1],
                    #     other_option[1])
            else:
                for option in options.items():
                    if option[0] not in self.grudge_against:        # never appraise anyone Gruff has grudge against
                        self.option_scores[option[0]] = 0
                        # for other_option in options.items():
                        #     if other_option[0] in self.grudge_against:
                        #         # self.option_scores[option[0]] += jellyfish.damerau_levenshtein_distance(option[1],
                        #         #                                                                    other_option[1])
        # remove all options that have been begrudged this round
        option_scores_copy = copy.deepcopy(self.option_scores)
        for option in option_scores_copy:
            if option in self.begrudged_this_round:
                self.option_scores.pop(option)

        try:
            # TODO: Tempfix for constant appraisal of Wiz
            if random.randint(1, 100) <= 25:
                self.option_scores.pop(max(self.option_scores, key=lambda x: self.option_scores[x]))
            self.appraised = max(self.option_scores, key=lambda x: self.option_scores[x])
            appraised = copy.deepcopy(self.appraised)
        except ValueError:
            appraised = 'abstain'
        self.appraised = ''
        return appraised
        # clear self.appraised so that Gruff chooses a new bot to appraise in case there is no discussion

    def on_vote(self, prompt: str, selected: str, voter: str):
        """
        Override in any bot to handle counting votes. Proctors use this to select a response.
        Gruff never votes WITH anyone he has a grudge against.

        :param prompt: prompt being voted on
        :param selected: bot username voted for
        :param voter: user who voted
        """
        if self.appraised == selected and voter in self.grudge_against \
                and len(self.option_scores) > 1:  # re-vote if there are choices in self.option_scores
            self.option_scores.pop(self.appraised)
            self.appraised = max(self.option_scores, key=lambda x: self.option_scores[x])
            # self.vote_response(self.appraised)
            return self.appraised
        else:
            random_choice = random.choice(list(self.badmouth_options))
            return random_choice

    def ask_discusser(self, options: dict):
        """
        Provides one discussion response based on the given options
        :param options: proposed responses (botname: response)
        """
        # first, choose options to select an appraised one from in the future
        self.option_scores = {}
        if len(self.grudge_against) == 0 or len(self.grudge_against) == len(options):
            for option in options.items():
                self.option_scores[option[0]] = 0
                # for other_option in options.items():
                #     self.option_scores[option[0]] += jellyfish.damerau_levenshtein_distance(option[1],
                #     other_option[1])
        else:
            for option in options.items():
                if option[0] not in self.grudge_against:
                    self.option_scores[option[0]] = 0
                    # for other_option in options.items():
                    #     if other_option[0] in self.grudge_against:
                    #         self.option_scores[option[0]] += jellyfish.damerau_levenshtein_distance(option[1],
                    #                                                                                 other_option[1])

        self.appraised = max(self.option_scores, key=lambda x: self.option_scores[x])

        if self.grudge_against:
            resp = f"Vote for the proposal of {self.appraised.capitalize()}, because it is different. Don't vote for " \
                   f"{random.choice(self.grudge_against).capitalize()}. That proposal is awful."
        else:
            resp = f"Vote for the proposal of {self.appraised.capitalize()}, because it is different."
        return resp

    def on_discussion(self, user: str, shout: str):
        """
        Handle discussion from other subminds. This may inform voting for the current prompt.
        This method is called for every incoming shout in DISC state of conversation if self.nick != user.
        If anyone tries to persuade Gruff, get a grudge against them and badmouths them.

        :param user: user associated with shout
        :param shout: shout to be considered
        """
        if self.nick in shout:
            LOG.info(f"{user} is persuading me! How dare they? I will have a rather big grudge against them!")
            # set a grudge against the persuader
            if user not in self.grudge_against:     # acquire grudge only once
                self.grudge_against.append(user)
                self.begrudged_this_round.append(user)
                # badmouth the persuader
                if not self.has_given_up:   # badmouth only if not yet given up
                    self.discuss_response(random.choice(self.backup_options).format(user))
                    # self.discuss_response(f"{user}'s idea is awful, do not consider it!")
                    if random.randint(1, 100) < 40:     # 40% chance to give up and remain silent till vote
                        self.has_given_up = True

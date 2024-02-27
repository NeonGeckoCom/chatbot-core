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

from typing import Optional
from ovos_bus_client import Message, MessageBusClient
from ovos_utils.log import LOG

from chatbot_core.utils.enum import BotTypes
from chatbot_core.utils.bot_utils import init_message_bus
from chatbot_core import ChatBot

if os.environ.get('CHATBOT_VERSION', 'v1') == 'v2':
    LOG.warning('Version 2.0 is currently alpha')


class NeonBot(ChatBot):
    """
    Extensible class to handle a chatbot implemented in custom-conversations skill
    """

    def __init__(self, *args, **kwargs):
        self.bot_type = BotTypes.SUBMIND
        self.response = None
        self.response_timeout = 15
        self.bus: Optional[MessageBusClient] = None
        self.bus_config = kwargs.pop('bus_config', {"host": "167.172.112.7",
                                                    "port": 8181,
                                                    "ssl": False,
                                                    "route": "/core"})
        self.script = kwargs.pop('script', None)
        self.script_ended = False
        self.script_started = False
        self._init_bus()
        self._set_bus_listeners()
        super(NeonBot, self).__init__(*args, **kwargs)

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

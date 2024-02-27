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

from typing import Optional
from chatbot_core.chatbot_abc import ChatBotABC
from ovos_utils.log import LOG


def get_class() -> Optional[type(ChatBotABC)]:
    """
    Get class matching current CHATBOT_VERSION

    :returns Class instance matching current version if any
    """
    from chatbot_core.v1 import ChatBot as ChatBot_v1
    from chatbot_core.v2 import ChatBot as ChatBot_v2

    version = get_current_version()
    LOG.debug(f"version={version}")
    chatbot_versions = {
        1: ChatBot_v1,
        2: ChatBot_v2
    }

    if version not in chatbot_versions:
        raise InvalidVersionError(f"{version} is not a valid version "
                                  f"({set(chatbot_versions.keys())}")
    return chatbot_versions.get(version)


def get_current_version() -> int:
    """
    Get an int representation of the configured Chatbot version to run
    """
    return 2 if os.environ.get('CHATBOT_VERSION',
                               'v1').lower() in ('v2', '2', 'version2') else 1


class InvalidVersionError(Exception):
    """
    Exception raised when invalid chatbots version is specified
    """

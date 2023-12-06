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

from ovos_utils.log import log_deprecation


def create_conversation_cycle():
    from chatbot_core.utils.conversation_utils import create_conversation_cycle
    log_deprecation("import from `chatbot_core.utils.conversation_utils`",
                    "2.3.1")
    return create_conversation_cycle()


def find_closest_answer(*args, **kwargs):
    from chatbot_core.utils.bot_utils import find_closest_answer
    log_deprecation("import from `chatbot_core.utils.bot_utils`",
                    "2.3.1")
    return find_closest_answer(*args, **kwargs)


def clean_up_bot(*args, **kwargs):
    from chatbot_core.utils.bot_utils import clean_up_bot
    log_deprecation("import from `chatbot_core.utils.bot_utils`",
                    "2.3.1")
    return clean_up_bot(*args, **kwargs)


def get_bots_in_dir(*args, **kwargs):
    from chatbot_core.utils.bot_utils import get_bots_in_dir
    log_deprecation("import from `chatbot_core.utils.bot_utils`",
                    "2.3.1")
    return get_bots_in_dir(*args, **kwargs)


def start_bots(*args, **kwargs):
    from chatbot_core.utils.bot_utils import start_bots
    log_deprecation("import from `chatbot_core.utils.bot_utils`",
                    "2.3.1")
    return start_bots(*args, **kwargs)

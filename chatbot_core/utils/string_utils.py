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

from copy import copy


def remove_prefix(prefixed_string: str, prefix: str):
    """
    Removes the specified prefix from the string
    :param prefixed_string: raw string to clean
    :param prefix: prefix to remove
    :return: string with prefix removed
    """
    if prefixed_string.startswith(prefix):
        return prefixed_string[len(prefix):].lstrip()
    return prefixed_string


def enumerate_subminds(subminds: list) -> str:
    """
    Enumerates bots in format of type "submind1(,submind2... and submindN)"
    where N is the number of subminds provided

    :param subminds: list of names to format
    :returns formatted string reflecting list of subminds provided
    """
    if len(subminds) == 0:
        return 'No one'
    if len(subminds) == 1:
        return subminds[0]
    subminds_copy = copy(subminds)
    last_submind = subminds_copy.pop()
    and_str = ", and " if len(subminds_copy) > 1 else " and "
    return f"{', '.join(subminds_copy)}{and_str}{last_submind}"

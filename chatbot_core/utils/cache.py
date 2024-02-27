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

from collections import OrderedDict
from typing import Optional


class FIFOCache:

    def __init__(self, capacity: int = 10):
        """
        Initialize an instance of the first-in-first-out cache with a set capacity
        :param capacity: a maximum number of entries to store in the cache at the same time
        """
        self.cache = OrderedDict()
        self.capacity = capacity

    def get(self, key: str) -> Optional[str]:
        """
        Lookup the cache using a string key
        :param key: a key in the key-value pair
        :return: a value associated with the provided key or None
        """
        if key not in self.cache:
            return None
        else:
            return self.cache[key]

    def put(self, key: str, value: str) -> None:
        """
        Put the key-value into cache if key not in the cache already
        :param key: a key to use in the cache dict
        :param value: a value associated with the key
        :return: None
        """
        if key not in self.cache:
            self.cache[key] = value
            self.cache.move_to_end(key)
            if len(self.cache) > self.capacity:
                self.cache.popitem(last=False)

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
from klat_connector.mq_klat_api import KlatAPIMQ


class ChatBot(KlatAPIMQ):

    def handle_kick_out(self, channel, method, _, body):
        """Handles incoming request to chat bot"""
        body_data = b64_to_dict(body)
        if body_data.get('receiver', None) == self.nick:
            self.current_conversations.remove(body_data.get('cid', None))

    def handle_invite(self, channel, method, _, body):
        """Handles incoming request to chat bot"""
        body_data = b64_to_dict(body)
        if body_data.get('cid', None) and body.get('receiver', None) == self.nick:
            self.current_conversations.add(body_data['cid'])

    def _setup_listeners(self):
        super()._setup_listeners()
        self.register_consumer('invitation', self.vhost, 'invite', self.handle_invite, self.default_error_handler)
        self.register_consumer('kick out', self.vhost, 'kick_out', self.handle_kick_out, self.default_error_handler)

import os
import time
import unittest

from chatbot_core.utils.bot_utils import run_mq_bot
from .mocks import ChatBotObserverMock


@unittest.skip(reason="Testing requires MQ server configuration")
class TestV2ProctoredConversation(unittest.TestCase):
    # os.environ['CHATBOT_VERSION'] = 'v2'
    # test_cid = 'test_conversation'
    # test_vhost = '/test_chatbots'
    # participating_bots = ("hodor", "wiz", "pard")
    # facilitators = ("proctor",)
    # for bot in participating_bots + facilitators:
    #     run_mq_bot(bot, test_vhost, run_kwargs={"run_sync": True,
    #                                             "run_consumers": True})
    # time.sleep(3)
    # observer = ChatBotObserverMock(config={},  # TODO: Define this config
    #                                service_name='mock_chatbot_observer')
    # observer.run(run_consumers=True, run_sync=False)

    def setUp(self) -> None:
        for bot in self.participating_bots.values():
            for consumer in bot.consumers.values():
                self.assertTrue(consumer.is_alive())

    def test_01_invite_bots(self):
        for bot in self.participating_bots:
            self.observer.invite_bot(bot_name=bot, cid=self.test_cid)
        time.sleep(12)

    def test_11_send_prompt(self):
        self.observer.send_prompt(msg_text='Is the Earth flat?')

    def test_12_send_mock_prompt_results(self):
        current_cid_data = {'userID': 'a5a8963b9f924bec8d69',
                            'messageText': '@proctor @pard @wiz',
                            'messageID': '3628cdf9-53cd-4e35-f607-0aa534a55b4e',
                            'attachments': [],
                            'timeCreated': 1650926390,
                            'message_id': '4554e4b10a1d43e1b667caacaa3567f2',
                            'prompt': {'cid': '6222367739332855a5cab2b6',
                                       'userID': 'a5a8963b9f924bec8d69',
                                       'messageText': 'what is the size of Pacific Ocean?',
                                       'messageID': '7f61c539-bec2-4151-924a-65187cb56db7',
                                       'attachments': [],
                                       'timeCreated': 1650926421,
                                       'message_id': '76be6fdd9641437d8e3435c722ee68b0',
                                       'prompt_id': '8f292a9683de402a9d65438267e77578'},
                            'is_active': True,
                            'available_subminds': ['pard-73ad4e5cae2049c4862a1ef121f6cd4a',
                                                   'wiz-a8fa6d5d1625421b8bd0d602cef0f639'],
                            'participating_subminds': ['pard-73ad4e5cae2049c4862a1ef121f6cd4a',
                                                       'wiz-a8fa6d5d1625421b8bd0d602cef0f639'],
                            'proposed_responses': {'pard-73ad4e5cae2049c4862a1ef121f6cd4a': 'Good conversation makes for good partners, don’t you think?',
                                                   'wiz-a8fa6d5d1625421b8bd0d602cef0f639': 'I do not have information about "the size"'},
                            'submind_opinions': {'pard-73ad4e5cae2049c4862a1ef121f6cd4a': 'Who wants to be friends?',
                                                 'wiz-a8fa6d5d1625421b8bd0d602cef0f639': "pard-73ad4e5cae2049c4862a1ef121f6cd4a's proposal is most factual. Vote for pard-73ad4e5cae2049c4862a1ef121f6cd4a."},
                            'votes': {'pard-73ad4e5cae2049c4862a1ef121f6cd4a': 'abstain', 'wiz-a8fa6d5d1625421b8bd0d602cef0f639': 'pard-73ad4e5cae2049c4862a1ef121f6cd4a'},
                            'votes_per_submind': {'pard-73ad4e5cae2049c4862a1ef121f6cd4a': ['wiz-a8fa6d5d1625421b8bd0d602cef0f639']},
                            'winner': 'pard-73ad4e5cae2049c4862a1ef121f6cd4a'}
        # TODO: implement Scorekeeper testing
        # scorekeeper_bot.send_shout(shout='!MSG:SAVE_PROMPT_RESULTS',
        #                            cid=cid,
        #                            omit_reply=True,
        #                            conversation_context=current_cid_data)

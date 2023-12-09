import json
import re
import time
from typing import Optional

import pika
from ovos_utils.log import LOG
from neon_mq_connector import MQConnector
from neon_utils.socket_utils import b64_to_dict


class ChatBotObserverMock(MQConnector):

    def __init__(self, config: Optional[dict], service_name: str):
        super().__init__(config, service_name)
        self.vhost = '/test_chatbots'
        self.register_consumer(name='user_message',
                               vhost=self.vhost,
                               queue='chatbot_user_message',
                               callback=self.handle_user_message,
                               on_error=self.default_error_handler,
                               auto_ack=False)
        self.connected_bots = {}

    def invite_bot(self, bot_name, cid):
        r = re.compile(bot_name)
        matched_bot = [nick for nick in list(self.connected_bots.items()) if r.match(nick)][0]
        with self.create_mq_connection(self.vhost) as mq_connection:
            self.emit_mq_message(connection=mq_connection,
                                 queue=f'{matched_bot}_invite',
                                 exchange='',
                                 request_data={'cid': cid})
            LOG.info(f'{matched_bot} invited to {cid}')
        return matched_bot

    def send_prompt(self, msg_text):
        msg_text = f'!prompt: {msg_text}'
        with self.create_mq_connection(self.vhost) as mq_connection:
            self.emit_mq_message(connection=mq_connection,
                                 queue='chatbot_user_message',
                                 exchange='',
                                 request_data={'bots': ['proctor'],
                                               'messageText': msg_text})
        LOG.info(f'Prompt: {msg_text} emitted successfully')

    def handle_user_message(self,
                            channel: pika.channel.Channel,
                            method: pika.spec.Basic.Return,
                            properties: pika.spec.BasicProperties,
                            body: bytes):
        """
            Handles messages from users

            :param channel: MQ channel object (pika.channel.Channel)
            :param method: MQ return method (pika.spec.Basic.Return)
            :param properties: MQ properties (pika.spec.BasicProperties)
            :param body: request body (bytes)

        """
        if body and isinstance(body, bytes):
            dict_data = b64_to_dict(body)
            LOG.info(f'Received bot requesting data: {dict_data}')
            requested_bots = json.loads(dict_data.pop('bots', []))
            for requested_nick in requested_bots:
                matched_bot = self.invite_bot(bot_name=requested_nick, cid=dict_data.get('cid'))
                time.sleep(2)
                self.emit_message_to_bot(nick=matched_bot, dict_data=dict_data)
        else:
            raise TypeError(f'Invalid body received, expected: bytes string; got: {type(body)}')

    def emit_message_to_bot(self, nick, dict_data):
        """
            Wrapper for emitting message to the bot

            :param nick: target bot nickname
            :param dict_data: dictionary with the data to emit
        """
        prompt_prefix = '!prompt:'
        with self.create_mq_connection(self.vhost) as mq_connection:
            if dict_data['messageText'].lower().startswith(prompt_prefix):
                esc_regex = re.compile(re.escape(prompt_prefix), re.IGNORECASE)
                dict_data['messageText'] = esc_regex.sub('', dict_data['messageText']).strip()
                LOG.info(f'Received prompting message: {dict_data["messageText"]}')
                self.publish_message(connection=mq_connection,
                                     request_data=dict_data,
                                     exchange='prompt')
            else:
                self.emit_mq_message(connection=mq_connection,
                                     queue=f'{nick}_user_message',
                                     exchange='',
                                     request_data=dict_data)

    def handle_chatbot_connection(self,
                                  channel: pika.channel.Channel,
                                  method: pika.spec.Basic.Return,
                                  properties: pika.spec.BasicProperties,
                                  body: bytes):
        """
            Handles chatbot connection request

            :param channel: MQ channel object (pika.channel.Channel)
            :param method: MQ return method (pika.spec.Basic.Return)
            :param properties: MQ properties (pika.spec.BasicProperties)
            :param body: request body (bytes)

        """
        if body and isinstance(body, bytes):
            dict_data = b64_to_dict(body)
            if dict_data.get('bot_type', None):
                new_nick = dict_data.pop('nick', None)
                if new_nick in list(self.connected_bots):
                    LOG.warning(f'Skipping connection attempt from "{new_nick}": its already connected')
                else:
                    self.connected_bots[new_nick] = dict_data
                    LOG.info(f'{new_nick} added to connected bots')
            else:
                LOG.debug('Skip non-bot connection')

    def handle_chatbot_disconnection(self,
                                     channel: pika.channel.Channel,
                                     method: pika.spec.Basic.Return,
                                     properties: pika.spec.BasicProperties,
                                     body: bytes):
        """
            Handles chatbot disconnection request

            :param channel: MQ channel object (pika.channel.Channel)
            :param method: MQ return method (pika.spec.Basic.Return)
            :param properties: MQ properties (pika.spec.BasicProperties)
            :param body: request body (bytes)

        """
        if body and isinstance(body, bytes):
            dict_data = b64_to_dict(body)
            new_nick = dict_data.pop('nick', None)
            if new_nick in list(self.connected_bots):
                self.connected_bots.pop(new_nick, None)
                LOG.warning(f'{new_nick} removed from connected bots')
            else:
                self.connected_bots[new_nick] = dict_data
                LOG.info(f'{new_nick} added to connected bots')

#!/usr/bin/env python3
import traceback
from time import sleep
from chatbot_core.logger import LOG
from .client import MessageBusClient


def on_message(message):
    LOG.info(str(message))


def main():
    sleep(0.5)
    client = MessageBusClient()
    client.on("message", on_message)
    client.run_forever()


if __name__ == '__main__':
    # Run loop trying to reconnect if there are any issues starting
    # the websocket
    while True:
        try:
            main()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            LOG.error(e)
            traceback.print_exc()

# NEON AI (TM) SOFTWARE, Software Development Kit & Application Development System
#
# Copyright 2008-2020 Neongecko.com Inc. | All Rights Reserved
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
# US Patents 2008-2020: US7424516, US20140161250, US20140177813, US8638908, US8068604, US8553852, US10530923, US10530924
# China Patent: CN102017585  -  Europe Patent: EU2156652  -  Patents Pending

import inspect
import logging
import os
import pkgutil
import socket
import sys

# import chatbots.bots

from datetime import datetime

from klat_connector import start_socket
from chatbot_core import LOG, ChatBot


def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]


SERVER = "0000.us" if ".112.7" in get_ip_address() else "2222.us"


def get_bots_in_dir(bot_path: str) -> dict:
    """
    Gets all ChatBots in the given directory, imports them, and returns a dict of their names to modules.
    :param bot_path: file path containing bots
    :return: dict of bot name:ChatBot object
    """

    # Make sure we have a path and not a filename
    bot_path = bot_path if os.path.isdir(bot_path) else os.path.dirname(bot_path)

    # Get all bots in the requested directory
    sys.path.append(bot_path)
    bot_names = [name for _, name, _ in pkgutil.iter_modules([bot_path])]
    bots = {}

    for mod in bot_names:
        module = __import__(mod)
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # TODO: Why are facilitators not subclassed ChatBots? DM
            if name != "ChatBot" and (issubclass(obj, ChatBot) or (mod in name and isinstance(obj, type))):
                bots[mod.lower()] = obj
    LOG.debug(bots)
    return bots


def start_bots(domain: str = None, bot_dir: str = None, username: str = None, password: str = None, server: str = None):
    """
    Start all of the bots in the given bot_dir and connect them to the given domain
    :param domain: Domain to put bots in
    :param bot_dir: Path containing bots to start
    :param username: Username to login with (or bot name if not defined)
    :param password: Password to login with (or None to connect as guest)
    :param server: Klat server url to connect to
    """

    domain = domain or "chatbotsforum.org"
    bot_dir = bot_dir or os.getcwd()
    server = server or SERVER

    bots_to_start = get_bots_in_dir(bot_dir)

    # Catch no bots found
    if len(bots_to_start.keys()) == 0:
        LOG.warning(f"No bots in: {bot_dir}")
        # TODO: Maybe some recursive check here instead of hard-coded dirs DM
        # Try getting from repo default location
        if os.path.isdir(os.path.join(bot_dir, "bots")):
            bots_in_dir = get_bots_in_dir(os.path.join(bot_dir, "bots"))
        else:
            bots_in_dir = {}
        # Check for repo facilitators
        if os.path.isdir(os.path.join(bot_dir, "facilitators")):
            facilitators = get_bots_in_dir(os.path.join(bot_dir, "bots"))
            bots_to_start = {**bots_in_dir, **facilitators}
        else:
            bots_to_start = bots_in_dir

    logging.getLogger("klat_connector").setLevel(logging.WARNING)
    proctor = None

    # Start a socket for each unique bot, bots handle login names
    for name, bot in bots_to_start.items():
        try:
            user = username or name
            b = bot(start_socket(server, 8888), domain, user, password, True)
            if b.bot_type == "proctor":
                proctor = b
        except Exception as e:
            LOG.error(name)
            LOG.error(e)
            LOG.error(bot)
    LOG.info(">>>STARTED<<<")
    try:
        while True:
            pass
    except KeyboardInterrupt:
        LOG.info("exiting")
        if proctor:
            proctor.pending_prompts.put(None)
            proctor.thread.join(30)


def cli_start_bots():
    """
    Entry Point to start bots from a Console Script
    """
    import argparse

    parser = argparse.ArgumentParser(description="Start some chatbots")
    parser.add_argument("--domain", dest="domain", default="chatbotsforum.org",
                        help="Domain to connect to (default: chatbotsforum.org)", type=str)
    parser.add_argument("--bots", dest="bot_dir",
                        help="Path to chatbots (default: ./)", type=str)
    parser.add_argument("--username", dest="username",
                        help="Klat username for bot", type=str)
    parser.add_argument("--password", dest="password",
                        help="Klat password for bot", type=str)
    parser.add_argument("--server", dest="server", default="0000.us",
                        help="Klat server (default: 0000.us", type=str)
    args = parser.parse_args()
    LOG.debug(args)
    start_bots(args.domain, args.bot_dir, args.username, args.password, args.server)


def debug_bots(bot_dir: str = os.getcwd()):
    """
    Debug bots in the passed directory
    :param bot_dir: directory containing the bot to test
    """

    # Try handling passed directory
    if len(sys.argv) > 1:
        arg_dir = os.path.expanduser(sys.argv[1])
        bot_dir = arg_dir if os.path.exists(arg_dir) else bot_dir

    logging.getLogger("chatbots").setLevel(logging.WARNING)
    logging.getLogger("klat_connector").setLevel(logging.WARNING)

    subminds = get_bots_in_dir(bot_dir)

    # Options to exit the interactive shell
    stop_triggers = ["bye", "see you later", "until next time", "have a great day", "goodbye"]
    running = True
    while running:
        try:
            print(f'BOTS: {subminds.keys()}.\n'
                  f'Please choose a bot to talk to')
            bot_name = input('[In]: ')
            if bot_name.lower() in subminds:
                bot = subminds[bot_name](start_socket("2222.us", 8888), None, None, None, on_server=False)
                while running:
                    utterance = input('[In]: ')
                    response = bot.ask_chatbot('Tester', utterance, datetime.now().strftime("%I:%M:%S %p"))
                    print(f'[Out]: {response}')
                    if utterance.lower() in stop_triggers:
                        running = False
                        LOG.warning("STOP RUNNING")
            else:
                print(f'BOTS: {subminds.keys()}.\n'
                      f'This bot does not exist. Please choose a valid bot to talk to')
        except KeyboardInterrupt:
            running = False
            LOG.warning("STOP RUNNING")
        except EOFError:
            running = False
        LOG.warning("Still Running")
    LOG.warning("Done Running")
    exit(0)

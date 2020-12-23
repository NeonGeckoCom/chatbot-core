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
import time

# from socketio import Client
from multiprocessing import Process, Event, synchronize

import sys

# import chatbots.bots

from datetime import datetime

import yaml
from klat_connector import start_socket
from chatbot_core import LOG, ChatBot


def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
    return ip


ip = get_ip_address()
if ip == "64.34.186.120":  # Test
    SERVER = "2222.us"
elif ip == "64.225.115.136":  # Cert
    SERVER = "5555.us"
elif ip == "167.172.112.7":  # Prod
    SERVER = "0000.us"
else:
    # Default external connections to production server
    SERVER = "0000.us"


def _threaded_start_bot(bot, addr: str, port: int, domain: str, user: str, password: str, event: synchronize.Event):
    """
    Helper function for _start_bot
    """
    instance = bot(start_socket(addr, port), domain, user, password, True)
    event.clear()
    event.wait()
    instance.exit()
    event.clear()


def _start_bot(bot, addr: str, port: int, domain: str, user: str, password: str)\
        -> (Process, synchronize.Event):
    """
    Creates a thread and starts the passed bot with passed parameters
    :param bot: ChatBot to instantiate
    :param addr: Server address to connect to
    :param port: Server socketIO port
    :param domain: Starting domain
    :param user: Username to login as
    :param password: Password to login with
    :returns: Process bot instance is attached to
    """
    event = Event()
    event.set()
    thread = Process(target=_threaded_start_bot, args=(bot, addr, port, domain, user, password, event))
    thread.daemon = True
    thread.start()
    while event.is_set():
        time.sleep(1)
    return thread, event


def get_bots_in_dir(bot_path: str, names_to_consider: str = os.environ.get("bot-names", False)) -> dict:
    """
    Gets all ChatBots in the given directory, imports them, and returns a dict of their names to modules.
    :param bot_path: absolute file path containing bots
    :param names_to_consider: limit imported instances to certain list
    :return: dict of bot name:ChatBot object
    """
    bots = {}

    # Make sure we have a path and not a filename
    bot_path = bot_path if os.path.isdir(bot_path) else os.path.dirname(bot_path)
    # Get all bots in the requested directory
    bot_names = [name for _, name, _ in pkgutil.iter_modules([bot_path])]
    # only specified bot names
    if names_to_consider:
        bot_names = list(set(bot_names) & set(names_to_consider.split(',')))
    if bot_names:
        sys.path.append(bot_path)

        for mod in bot_names:
            module = __import__(mod)
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # TODO: Why are facilitators not subclassed ChatBots? DM
                if name != "ChatBot" and (issubclass(obj, ChatBot) or (mod in name and isinstance(obj, type))):
                    bots[mod] = obj
        LOG.debug(bots)
    return bots


def load_credentials_yml(cred_file: str) -> dict:
    """
    Loads a credentials yml file and returns a dictionary of parsed credentials per-module
    :param cred_file: Input yml file containing credentials for bot modules
    :return: dict of bot modules to usernames and passwords
    """
    with open(cred_file, 'r') as f:
        credentials_dict = yaml.safe_load(f)
    return credentials_dict


def start_bots(domain: str = None, bot_dir: str = None, username: str = None, password: str = None, server: str = None,
               cred_file: str = None, bot_name: str = None, excluded_bots: list = None):
    """
    Start all of the bots in the given bot_dir and connect them to the given domain
    :param domain: Domain to put bots in
    :param bot_dir: Path containing bots to start
    :param username: Username to login with (or bot name if not defined)
    :param password: Password to login with (or None to connect as guest)
    :param server: Klat server url to connect to
    :param cred_file: Path to a credentials yml file
    :param bot_name: Optional name of the bot to start (None for all bots)
    :param excluded_bots: Optional list of bots to exclude from launching
    """

    domain = domain or "chatbotsforum.org"
    bot_dir = bot_dir or os.getcwd()
    bot_dir = os.path.expanduser(bot_dir)
    server = server or SERVER
    LOG.debug(f"Starting bots on server: {server}")
    bots_to_start = get_bots_in_dir(bot_dir)

    # Catch no bots found
    if len(bots_to_start.keys()) == 0:
        LOG.info(f"No bots in: {bot_dir}")
        for d in os.listdir(bot_dir):
            try:
                if str(d) not in ("__pycache__", "tests", "venv", "torchmoji") and not d.startswith(".") \
                        and os.path.isdir(os.path.join(bot_dir, d)):
                    LOG.info(f"Found bots dir {d}")
                    bots_to_start = {**get_bots_in_dir(os.path.join(bot_dir, d)), **bots_to_start}
            except Exception as e:
                LOG.error(e)

    LOG.info(bots_to_start.keys())
    logging.getLogger("klat_connector").setLevel(logging.WARNING)
    logging.getLogger("tensorflow").setLevel(logging.ERROR)
    # proctor = None

    # Load credentials
    if cred_file:
        cred_file = os.path.expanduser(cred_file)
        if not os.path.isfile(cred_file) and os.path.isfile(os.path.join(os.getcwd(), cred_file)):
            cred_file = os.path.join(os.getcwd(), cred_file)
        else:
            cred_file = None
    elif os.path.isfile(os.path.join(os.getcwd(), "credentials.yml")):
        cred_file = os.path.join(os.getcwd(), "credentials.yml")

    LOG.debug(f"Found credentials at: {cred_file}")
    if cred_file:
        credentials = load_credentials_yml(cred_file)
    else:
        credentials = {}

    processes = []

    # Check for specified bot to start
    if bot_name:
        LOG.debug(f"Got requested bot:{bot_name}")
        bot = bots_to_start.get(bot_name)
        if bot:
            try:
                user = username or credentials.get(bot_name, {}).get("username")
                password = password or credentials.get(bot_name, {}).get("password")
                p, _ = _start_bot(bot, server, 8888, domain, user, password)
                processes.append(p)
                # bot(start_socket(server, 8888), domain, user, password, True)
            except Exception as e:
                LOG.error(e)
        else:
            LOG.error(f"{bot_name} is not a valid bot!")
            return
    else:
        if excluded_bots:
            for name in excluded_bots:
                if name in bots_to_start.keys():
                    bots_to_start.pop(name)

        # Start Proctor first if in the list of bots to start
        if "Proctor" in bots_to_start.keys():
            bot = bots_to_start.pop("Proctor")
            try:
                user = username or credentials.get("Proctor", {}).get("username")
                password = password or credentials.get("Proctor", {}).get("password")
                process, event = _start_bot(bot, server, 8888, domain, user, password)
                processes.append(process)
            except Exception as e:
                LOG.error(e)
                LOG.error(bot)

        # Start a socket for each unique bot, bots handle login names
        for name, bot in bots_to_start.items():
            LOG.debug(f"Starting: {name}")
            try:
                user = username or credentials.get(name, {}).get("username")
                password = password or credentials.get(name, {}).get("password")
                process, event = _start_bot(bot, server, 8888, domain, user, password)
                processes.append(process)
            except Exception as e:
                LOG.error(name)
                LOG.error(e)
                LOG.error(bot)
    LOG.info(">>>STARTED<<<")
    try:
        # Wait for an event that will never come
        runner = Event()
        runner.clear()
        runner.wait()
    except KeyboardInterrupt:
        LOG.info("exiting")
        for p in processes:
            p.join()


def cli_start_bots():
    """
    Entry Point to start bots from a Console Script
    """
    import argparse

    parser = argparse.ArgumentParser(description="Start some chatbots")
    parser.add_argument("--domain", dest="domain", default="chatbotsforum.org",
                        help="Domain to connect to (default: chatbotsforum.org)", type=str)
    parser.add_argument("--dir", dest="bot_dir",
                        help="Path to chatbots (default: ./)", type=str)
    parser.add_argument("--bot", dest="bot_name",
                        help="Optional bot name to run a single bot only", type=str)
    parser.add_argument("--credentials", dest="cred_file",
                        help="Optional path to YAML credentials", type=str)
    parser.add_argument("--username", dest="username",
                        help="Klat username for a single bot", type=str)
    parser.add_argument("--password", dest="password",
                        help="Klat password for a single bot", type=str)
    parser.add_argument("--server", dest="server", default=SERVER,
                        help=f"Klat server (default: {SERVER})", type=str)
    parser.add_argument("--debug", dest="debug", action='store_true',
                        help="Enable more verbose log output")
    parser.add_argument("--bot-names", dest="bot-names",
                        help="comma separated list of bots to include in running", type=str)
    parser.add_argument("--exclude", dest="exclude",
                        help="comma separated list of bots to exclude from running", type=str)
    args = parser.parse_args()

    if args.debug:
        logging.getLogger("chatbots").setLevel(logging.DEBUG)
        logging.getLogger("chatbot").setLevel(logging.DEBUG)
    else:
        logging.getLogger("chatbots").setLevel(logging.INFO)
        logging.getLogger("chatbot").setLevel(logging.INFO)

    if args.exclude:
        excluded_bots = [name.strip() for name in args.exclude.split(",")]
    else:
        excluded_bots = None
    LOG.debug(args)
    start_bots(args.domain, args.bot_dir, args.username, args.password, args.server, args.cred_file, args.bot_name,
               excluded_bots)


def cli_stop_bots():
    """
    Stops all start-klat-bot instances
    """
    import psutil

    procs = {p.pid: p.info for p in psutil.process_iter(['name'])}
    for pid, name in procs.items():
        if "start-klat-bots" in name:
            psutil.Process(pid).kill()
    # TODO: Troubleshoot psutil kill DM
    os.system("killall start-klat-bots")


def debug_bots(bot_dir: str = os.getcwd()):
    """
    Debug bots in the passed directory
    :param bot_dir: directory containing the bot to test
    """
    # TODO: Generalize this to testing different modules? Leave one method for selecting a bot and then create an
    #       options menu for this interactive testing, along with automated discusser and appraiser testing.
    #       Automated testing could use pre-built response objects, or run n other bots and handle their outputs offline

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
            if bot_name in subminds:
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


def clean_up_bot(bot: ChatBot):
    """
    Performs any standard cleanup for a bot on destroy
    :param bot: ChatBot instance to clean up
    """
    if not isinstance(bot, ChatBot):
        raise TypeError
    bot.socket.disconnect()
    if hasattr(bot, "shout_queue"):
        bot.shout_queue.put(None)
    if hasattr(bot, "shout_thread"):
        bot.shout_thread.join(0)

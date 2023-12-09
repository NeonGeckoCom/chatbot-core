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

import inspect
import logging
import os
import random
import time
import sys
import yaml

from typing import Optional, Callable, Dict, List
from multiprocessing import Process, Event, synchronize
from threading import Thread, current_thread
from ovos_bus_client import Message, MessageBusClient
from datetime import datetime
from ovos_utils.xdg_utils import xdg_config_home
from ovos_utils.log import LOG, log_deprecation
from neon_utils.net_utils import get_ip_address

from chatbot_core.chatbot_abc import ChatBotABC
from chatbot_core.v2 import ChatBot as ChatBotV2
from chatbot_core.v1 import ChatBot as ChatBotV1


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

# active_server = None
runner = Event()


def get_ip_address():
    log_deprecation('Import from `neon_utils.net_utils` directly', "2.3.0")
    return get_ip_address()


def _threaded_start_bot(bot, addr: str, port: int, domain: str, user: str,
                        password: str, event: synchronize.Event,
                        is_prompter: bool):
    """
    Helper function for _start_bot
    """
    from klat_connector import start_socket
    # TODO: Deprecate
    if len(inspect.signature(bot).parameters) == 6:
        instance = bot(start_socket(addr, port), domain, user, password, True,
                       is_prompter)
    elif len(inspect.signature(bot).parameters) == 5:
        if is_prompter:
            LOG.error(f"v2 Bot found, prompter functionality will "
                      f"not be enabled! {bot}")
        instance = bot(start_socket(addr, port), domain, user, password, True)
    else:
        LOG.error(f"Bot params unknown: {inspect.signature(bot).parameters}")
        instance = bot(start_socket(addr, port))
    if is_prompter:  # Send intial prompt if this bot is a prompter
        instance.send_shout(instance.initial_prompt)
    event.clear()
    event.wait()

    # Exit when event is set and then clear event to notify calling function
    instance.exit()
    event.clear()


def _start_bot(bot, addr: str, port: int, domain: str, user: str,
               password: str, is_prompter: bool = False)\
        -> (Process, synchronize.Event):
    """
    Creates a thread and starts the passed bot with passed parameters
    :param bot: ChatBot to instantiate
    :param addr: Server address to connect to
    :param port: Server socketIO port
    :param domain: Starting domain
    :param user: Username to login as
    :param password: Password to login with
    :param is_prompter: True if bot is to generate prompts for the Proctor
    :returns: Process bot instance is attached to
    """
    # TODO: Deprecate
    event = Event()
    event.set()
    thread = Process(target=_threaded_start_bot,
                     args=(bot, addr, port, domain, user, password, event,
                           is_prompter))
    thread.daemon = True
    thread.start()
    while event.is_set():
        time.sleep(0.2)
    return thread, event


def get_bots_in_dir(bot_path: str,
                    names_to_consider: str = None) -> dict:
    """
    Gets all ChatBots in the given directory, imports them, and returns a
        dict of their names to modules.
    :param bot_path: absolute file path containing bots
    :param names_to_consider: limit imported instances to certain list
    :return: dict of bot name:ChatBot object
    """
    names_to_consider = names_to_consider or os.environ.get("bot-names")
    import pkgutil
    log_deprecation("This functionality is deprecated. Bots should specify a "
                    "`neon.plugin.chatbot` entrypoint", "3.0.0")
    bots = {}

    try:
        # Make sure we have a path and not a filename
        bot_path = bot_path if os.path.isdir(bot_path) else \
            os.path.dirname(bot_path)
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
                    if name != "ChatBot" and (issubclass(obj, ChatBotABC) or
                                              (mod in name and
                                               isinstance(obj, type))):
                        bots[mod] = obj
            LOG.debug(bots)
    except Exception as e:
        LOG.error(e)
    return bots


def load_credentials_yml(cred_file: str) -> dict:
    """
    Loads a credentials yml file and returns a dictionary of parsed credentials
    per-module.
    :param cred_file: Input yml file containing credentials for bot modules
    :return: dict of bot modules to usernames and passwords
    """
    log_deprecation(f"This functionality is deprecated. Configuration should "
                    f"be specified in `{xdg_config_home()}/neon/chatbots.yaml`",
                    "3.0.0")
    with open(cred_file, 'r') as f:
        credentials_dict = yaml.safe_load(f)
    return credentials_dict


def _start_bot_processes(bots_to_start: dict, username: str, password: str,
                         credentials: dict, server: str, domain: str) -> list:
    # TODO: Deprecate
    processes = []

    # Start Proctor first if in the list of bots to start
    if "Proctor" in bots_to_start.keys():
        bot = bots_to_start.get("Proctor")
        try:
            user = username or credentials.get("Proctor", {}).get("username")
            password = password or credentials.get("Proctor",
                                                   {}).get("password")
            process, event = _start_bot(bot, server, 8888, domain, user,
                                        password, False)
            processes.append(process)
        except Exception as e:
            LOG.error(e)
            LOG.error(bot)

    # Start a socket for each unique bot, bots handle login names
    for name, bot in bots_to_start.items():
        if name != "Proctor":
            LOG.debug(f"Starting: {name}")
            try:
                user = username or credentials.get(name, {}).get("username")
                password = password or credentials.get(name, {}).get("password")
                process, event = _start_bot(bot, server, 8888, domain, user,
                                            password, False)
                processes.append(process)
            except Exception as e:
                LOG.error(name)
                LOG.error(e)
                LOG.error(bot)
    return processes


def start_bots(domain: str = None, bot_dir: str = None, username: str = None,
               password: str = None, server: str = None, cred_file: str = None,
               bot_name: str = None, excluded_bots: list = None,
               handle_restart: bool = False, is_prompter: bool = False):
    """
    Start all the bots in the given bot_dir and connect them to the given domain
    :param domain: Domain to put bots in
    :param bot_dir: Path containing bots to start
    :param username: Username to login with (or bot name if not defined)
    :param password: Password to login with (or None to connect as guest)
    :param server: Klat server url to connect to
    :param cred_file: Path to a credentials yml file
    :param bot_name: Optional name of the bot to start (None for all bots)
    :param excluded_bots: Optional list of bots to exclude from launching
    :param handle_restart: If true, listens for a restart message from the
        server to restart chatbots
    :param is_prompter: If true, bot sends prompts to the Proctor and handles
        responses
    """
    log_deprecation("This method is deprecated. Bots should be loaded by "
                    "entrypoints.", "3.0.0")
    # TODO: Method for loading v1 bots by entrypoints
    # global active_server
    global runner
    domain = domain or "chatbotsforum.org"
    bot_dir = bot_dir or os.getcwd()
    bot_dir = os.path.expanduser(bot_dir)
    server = server or SERVER
    # active_server = server
    LOG.debug(f"Starting bots on server: {server}")
    bots_to_start = get_bots_in_dir(bot_dir)

    # Catch no bots found
    if len(bots_to_start.keys()) == 0:
        LOG.info(f"No bots in: {bot_dir}")
        for d in os.listdir(bot_dir):
            try:
                if str(d) not in ("__pycache__", "tests", "venv", "torchmoji",
                                  "ParlAI") and not d.startswith(".") \
                        and os.path.isdir(os.path.join(bot_dir, d)):
                    LOG.info(f"Found bots dir {d}")
                    bots_to_start = {**get_bots_in_dir(os.path.join(bot_dir,
                                                                    d)),
                                     **bots_to_start}
            except Exception as e:
                LOG.error(e)

    LOG.info(bots_to_start.keys())
    logging.getLogger("klat_connector").setLevel(logging.WARNING)
    logging.getLogger("tensorflow").setLevel(logging.ERROR)
    # proctor = None

    # Load credentials
    if cred_file:
        cred_file = os.path.expanduser(cred_file)
        if not os.path.isfile(cred_file) and \
                os.path.isfile(os.path.join(os.getcwd(), cred_file)):
            cred_file = os.path.join(os.getcwd(), cred_file)
        elif not os.path.isfile(cred_file):
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
            bots_to_start = {bot_name: bot}
            try:
                user = username or credentials.get(bot_name,
                                                   {}).get("username")
                password = password or credentials.get(bot_name,
                                                       {}).get("password")
                p, _ = _start_bot(bot, server, 8888, domain, user, password,
                                  is_prompter)
                processes.append(p)
                # bot(start_socket(server, 8888), domain, user, password, True)
            except Exception as e:
                LOG.error(e)
        else:
            LOG.error(f"{bot_name} is not a valid bot!")
            return
    # Else start all bots
    else:
        if excluded_bots:
            # Remove any excluded bots
            for name in excluded_bots:
                if name in bots_to_start.keys():
                    bots_to_start.pop(name)

        processes = _start_bot_processes(bots_to_start, username, password,
                                         credentials, server, domain)

    if handle_restart:
        log_deprecation("Messagebus connections to Neon Core will be "
                        "deprecated", "3.0.0")
        LOG.info(f"Setting restart listener for {server}")
        _listen_for_restart_chatbots(server)
    try:
        # runner = Event()
        while True:
            LOG.info(">>>STARTED<<<")
            # Wait for an event that will never come
            runner.clear()
            runner.wait()
            LOG.info(">>>RESTART REQUESTED<<<")
            # LOG.debug(f"procs={len(processes)} | {processes}")
            for p in processes:
                try:
                    LOG.debug(f"Terminating {p.pid}")
                    # processes.remove(p)
                    p.terminate()
                    time.sleep(1)
                    if p.is_alive():
                        LOG.warning(f"Process {p.pid} not terminated! "
                                    f"Killing..")
                        p.kill()
                        time.sleep(1)
                        if p.is_alive():
                            LOG.error(f"Process {p.pid} still alive!")
                except Exception as e:
                    LOG.error(e)
                    p.kill()
            LOG.debug(f"Processes ended")
            processes = _start_bot_processes(bots_to_start, username, password,
                                             credentials, server, domain)
    except KeyboardInterrupt:
        LOG.info("exiting")
        for p in processes:
            p.join()


def debug_bots(bot_dir: str = None):
    """
    Debug bots in the passed directory
    :param bot_dir: directory containing the bot to test
    """
    # TODO: Generalize this to testing different modules? Leave one method for
    #       selecting a bot and then create an options menu for this interactive
    #       testing, along with automated discusser and appraiser testing.
    #       Automated testing could use pre-built response objects, or run n
    #       other bots and handle their outputs offline
    from klat_connector.mach_server import MachKlatServer
    from ovos_config.config import Configuration
    server = MachKlatServer()
    Configuration()['socket_io'] = {"server": "0.0.0.0",
                                    "port": 8888}
    # TODO: Define alternate `ChatBot` base class with no server dependency
    if bot_dir:
        log_deprecation("Bots should be installed so they may be accessed by "
                        "entrypoint. Specifying a local directory will no "
                        "longer be supported", "2.3.1")
        subminds = get_bots_in_dir(bot_dir)
    else:
        subminds = _find_bot_modules()
    # Options to exit the interactive shell
    stop_triggers = ["bye", "see you later", "until next time",
                     "have a great day", "goodbye"]
    running = True
    while running:
        try:
            print(f'BOTS: {subminds.keys()}.\n'
                  f'Please choose a bot to talk to')
            bot_name = input('[In]: ')
            if bot_name in subminds:
                bot = run_sio_bot(bot_name)
                while running:
                    utterance = input('[In]: ')
                    response = bot.ask_chatbot('Tester', utterance,
                                               datetime.now().strftime(
                                                   "%I:%M:%S %p"))
                    print(f'[Out]: {response}')
                    if utterance.lower() in stop_triggers:
                        running = False
                        LOG.debug("STOP RUNNING")
            else:
                print(f'BOTS: {subminds.keys()}.\nThis bot does not exist.'
                      f' Please choose a valid bot to talk to')
        except KeyboardInterrupt:
            running = False
            LOG.warning("STOP RUNNING")
        except EOFError:
            running = False
    server.shutdown_server()
    LOG.info("Done Running")


def clean_up_bot(bot: ChatBotABC):
    """
    Performs any standard cleanup for a bot on destroy
    :param bot: ChatBot instance to clean up
    """
    from chatbot_core.v1 import ChatBot as V1

    if not isinstance(bot, ChatBotABC):
        raise TypeError(f"Expected ChatBot, got: {type(bot)}")
    if isinstance(bot, V1):
        bot.socket.disconnect()
    if hasattr(bot, "shout_queue"):
        bot.shout_queue.put(None)
    if hasattr(bot, "shout_thread"):
        if current_thread() != bot.shout_thread:
            bot.shout_thread.join(0)
    if hasattr(bot, "bus"):
        bot.bus.close()


def _restart_chatbots(message: Message):
    """
    Messagebus handler to restart chatbots on a server
    :param message: Message associated with request
    """
    # TODO: Deprecate in 3.0.0
    global runner
    LOG.debug(f"Restart received: {message.data} | {message.context}")
    runner.set()


def _listen_for_restart_chatbots(server: str):
    """
    Registers a messagebus listener to restart chatbots for the given server
    :param server: base url of the klat server messagebus to listen to
    """
    # TODO: Deprecate in 3.0.0
    if server == "2222.us":
        host = "64.34.186.120"
    elif server == "5555.us":
        host = "64.225.115.136"
    else:
        host = "167.172.112.7"
    LOG.debug(f"Listening for restart message on {host}")
    bus_config = {"host": host,
                  "port": 8181,
                  "ssl": False,
                  "route": "/core"}
    thread, bus = init_message_bus(bus_config)
    bus.on("restart chatbots", _restart_chatbots)


def init_message_bus(bus_config: dict = None) -> (Thread, MessageBusClient):
    """
    Connects to a Neon Core messagebus and returns the thread and bus.
    :param bus_config: messagebus configuration to use
    :return: Thread, messagebus object
    """
    log_deprecation("Messagebus connections to Neon Core will be deprecated",
                    "3.0.0")
    bus_config = bus_config or {"host": "167.172.112.7",
                                "port": 8181,
                                "ssl": False,
                                "route": "/core"}
    bus = MessageBusClient(bus_config["host"], bus_config["port"],
                           bus_config["route"], bus_config["ssl"])
    t = bus.run_in_thread()
    bus.connected_event.wait(10)
    LOG.info(f"Connected to Messagebus at: {bus_config['host']}")
    return t, bus


def generate_random_response(from_iterable: iter):
    """
    Generates some random bot response from the given options
    :param from_iterable: source iterable to get random value from
    """
    log_deprecation("Use `random.choice` directly", "3.0.0")
    return random.choice(from_iterable)


def find_closest_answer(algorithm: str = 'random', sentence: str = None,
                        options: dict = None) -> Optional[str]:
    """
    Determines which option is most similar to an input sentence
    :param algorithm: algorithm considered
    :param sentence: base sentence
    :param options: dict of option ID to response for comparison with `sentence`
    :returns: `option` ID with a value closest to `sentence`, None if requested
              algorithm fails
    """
    if not sentence:
        LOG.warning('Empty sentence supplied')
        return None
    if not options or len(options.keys()) == 0:
        LOG.warning('No options provided')
        return None
    if algorithm == 'random':
        closest_answer = random.choice(list(options.keys()))
    elif algorithm == 'bleu_score':
        try:
            import nltk
            nltk.download('punkt')
            from nltk import word_tokenize
            from nltk.translate.bleu_score import sentence_bleu
        except ImportError:
            LOG.warning("`nltk` not installed. install "
                        "`chatbot-core[lang]` to install NLU packages.")
            return None
        bleu_scores = []
        response_tokenized = word_tokenize(sentence.lower())
        for option in options.keys():
            opinion_tokenized = word_tokenize(options[option].lower())
            if len(opinion_tokenized) > 0:
                if min(len(response_tokenized), len(opinion_tokenized)) < 4:
                    weighting = 1.0 / min(len(response_tokenized),
                                          len(opinion_tokenized))
                    weights = tuple([weighting] * min(len(response_tokenized),
                                                      len(opinion_tokenized)))
                else:
                    weights = (0.25, 0.25, 0.25, 0.25)
                bleu_scores.append((option, sentence_bleu([response_tokenized],
                                                          opinion_tokenized,
                                                          weights=weights)))
        max_score = max([x[1] for x in
                         bleu_scores]) if len(bleu_scores) > 0 else 0
        closest_answer = random.choice(list(filter(lambda x: x[1] == max_score,
                                                   bleu_scores)))[0]
        LOG.info(f'Closest answer is {closest_answer}')
    elif algorithm == 'damerau_levenshtein_distance':
        closest_distance = None
        closest_answer = None
        try:
            import jellyfish
            for option in options.items():
                distance = jellyfish.damerau_levenshtein_distance(option[1],
                                                                  sentence)
                if not closest_distance or closest_distance > distance:
                    closest_distance = distance
                    closest_answer = option[0]
            LOG.info(f'Closest answer is {closest_answer}')
        except ImportError:
            jellyfish = None
            LOG.warning("`jellyfish` not installed. install "
                        "`chatbot-core[lang]` to install NLU packages.")
        except Exception as e:
            LOG.error(e)
    else:
        LOG.error(f'Unknown algorithm supplied:{algorithm}')
        return None
    return closest_answer


def grammar_check(func: Callable):
    """
    Decorator to add spelling/grammar checks to a function's output
    :param func: function to consider
    """
    try:
        from autocorrect import Speller
        spell = Speller()
    except ImportError:
        Speller = None
        LOG.error("autocorrect module not available. Install "
                  "`chatbot-core[extra-lgpl]` to use autocorrect.")
        spell = None

    def wrapper(*args, **kwargs):
        LOG.debug("Entered decorator")
        output = func(*args, **kwargs)
        if output and spell:
            LOG.debug(f"Received output: {output}")
            output = spell(output)
            LOG.debug(f"Processed output: {output}")
        return output

    return wrapper


def _find_bot_modules() -> Dict[str, type(ChatBotABC)]:
    """
    Method for locating all installed chatbots by entrypoint.
    """
    try:
        from importlib_metadata import entry_points
        bot_entrypoints = entry_points(group="neon.plugin.chatbot")
    except ImportError:
        entry_points = None
        import pkg_resources
        bot_entrypoints = pkg_resources.iter_entry_points("neon.plugin.chatbot")

    return {entry.name: entry.load() for entry in bot_entrypoints}


def run_mq_bot(chatbot_name: str, vhost: str = '/chatbots',
               run_kwargs: dict = None, init_kwargs: dict = None) -> ChatBotV2:
    """
    Get an initialized MQ Chatbot instance
    @param chatbot_name: chatbot entrypoint name and configuration key
    @param vhost: MQ vhost to connect to (default /chatbots)
    @param run_kwargs: kwargs to pass to chatbot `run` method
    @param init_kwargs: extra kwargs to pass to chatbot `__init__` method
    @returns: Started ChatBotV2 instance
    """
    from neon_utils.log_utils import init_log
    init_log(log_name=chatbot_name)
    os.environ['CHATBOT_VERSION'] = 'v2'
    run_kwargs = run_kwargs or dict()
    init_kwargs = init_kwargs or dict()
    bots = _find_bot_modules()
    clazz = bots.get(chatbot_name)
    if init_kwargs.get('config'):
        LOG.info(f"Config specified: {init_kwargs['config']}")
    if not clazz:
        raise RuntimeError(f"Requested bot `{chatbot_name}` not found in: "
                           f"{list(bots.keys())}")
    bot = clazz(service_name=chatbot_name, vhost=vhost, **init_kwargs)
    LOG.info(f"Starting {chatbot_name}")
    bot.run(**run_kwargs)
    LOG.info(f"Started {chatbot_name}")
    return bot


def run_sio_bot(chatbot_name: str, domain: str = None,
                is_prompter: bool = False) -> ChatBotV1:
    """
    Get an initialized SIO Chatbot instance
    @param chatbot_name: chatbot entrypoint name and configuration key
    @param domain: Initial domain to enter
    @param is_prompter: If true, submit prompts rather than contribute responses
    @returns: Started ChatBotV2 instance
    """
    from ovos_config.config import Configuration
    from klat_connector import start_socket
    sio_config = Configuration().get("socket_io", {})
    os.environ['CHATBOT_VERSION'] = 'v1'
    domain = domain or "chatbotsforum.org"
    bots = _find_bot_modules()
    clazz = bots.get(chatbot_name)
    if not clazz:
        raise RuntimeError(f"Requested bot `{chatbot_name}` not found in: "
                           f"{list(bots.keys())}")
    sock = start_socket(sio_config.get("server"), sio_config.get("port"))
    bot = clazz(socket=sock, domain=domain, is_prompter=is_prompter)
    LOG.info(f"Started {chatbot_name}")
    return bot


def run_all_bots(domain: str = None) -> List[ChatBotABC]:
    """
    Run all installed chatbots, connecting to the configured server, considering
    the value of the `CHATBOT_VERSION` envvar
    """
    bots = _find_bot_modules()
    from chatbot_core.utils.version_utils import get_current_version
    chatbot_version = get_current_version()
    chatbots = list()
    for bot in bots.keys():
        if chatbot_version == 1:
            chatbots.append(run_sio_bot(bot, domain=domain))
        elif chatbot_version == 2:
            chatbots.append(run_mq_bot(bot))
        else:
            from chatbot_core.utils.version_utils import InvalidVersionError
            raise InvalidVersionError(f"Unable to start chatbot with version: "
                                      f"{chatbot_version}")
    return chatbots


def run_local_discussion(prompter_bot: str):
    """
    Run all installed bots locally with a prompter to submit prompts for
    discussion.
    @param prompter_bot: name/entrypoint of bot to be used as a proctor
    """
    import click
    from ovos_config.config import Configuration
    # Override logging
    Configuration()['log_level'] = "ERROR"

    # Start local server
    from klat_connector import start_socket
    from klat_connector.mach_server import MachKlatServer
    server = MachKlatServer()

    # Load all installed subminds and facilitators
    os.environ['CHATBOT_VERSION'] = 'v1'
    bots = _find_bot_modules()
    chatbots = list()
    for name, clazz in bots.items():
        chatbots.append(clazz(socket=start_socket("0.0.0.0"), domain="local",
                              username=name, password=name))

    prompter_clazz = bots.get(prompter_bot)
    prompter = prompter_clazz(socket=start_socket("0.0.0.0"), domain="private",
                              is_prompter=True, username="Prompter",
                              password=prompter_bot)
    chatbots.append(prompter)
    LOG.info("Local Conversation started")
    # Make conversation output readable
    # TODO: prevent log output going to terminal

    def handle_shout(user, shout, cid, dom, timestamp):
        click.echo(f"{user.rjust(max((len(name) for name in bots)))} : {shout}")

    observer = ChatBotV1(socket=start_socket("0.0.0.0"), domain="local")
    observer.handle_shout = handle_shout

    prompter.send_shout("@proctor hello")
    from ovos_utils import wait_for_exit_signal
    wait_for_exit_signal()
    for bot in chatbots:
        bot.exit()
    server.shutdown_server()

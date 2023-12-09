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

import os
import argparse
import click

from os.path import expanduser, relpath
from ovos_utils.log import LOG, log_deprecation


@click.group("chatbots", cls=click.Group,
             no_args_is_help=True, invoke_without_command=True,
             help="Chatbot Core Commands\n\n"
                  "See also: chatbots COMMAND --help")
@click.option("--version", "-v", is_flag=True, required=False,
              help="Print the current version")
def chatbot_core_cli(version: bool = False):
    if version:
        from chatbot_core.version import __version__
        click.echo(f"chatbot-core version {__version__}")


@chatbot_core_cli.command(help="Start an MQ chatbot")
@click.argument("bot_entrypoint")
def start_mq_bot(bot_entrypoint):
    os.environ['CHATBOT_VERSION'] = 'v2'
    from chatbot_core.utils.bot_utils import run_mq_bot
    run_mq_bot(bot_entrypoint)


@chatbot_core_cli.command(help="Start a local single-bot session")
@click.option("--bot-dir", default=None,
              help="Path to legacy chatbots directory")
def debug_bots(bot_dir):
    from chatbot_core.utils.bot_utils import debug_bots
    bot_dir = expanduser(relpath(bot_dir)) if bot_dir else None
    debug_bots(bot_dir)


@chatbot_core_cli.command(help="Start a local CBF-style conversation")
@click.option("--prompter", "-p", help="ID of Chatbot to submit prompts")
def run_local_discussion(prompter):
    from chatbot_core.utils.bot_utils import run_local_discussion
    run_local_discussion(prompter)


# Below are deprecated entrypoints
def cli_start_mq_bot():
    """
    Entrypoint to start an MQ chatbot
    """
    os.environ['CHATBOT_VERSION'] = 'v2'
    from chatbot_core.utils.bot_utils import run_mq_bot
    log_deprecation("Use `chatbots start-mq-bot`", "3.0.0")
    parser = argparse.ArgumentParser(description="Start a chatbot")
    parser.add_argument("--bot", dest="bot_name",
                        help="Chatbot entrypoint name", type=str)
    args = parser.parse_args()
    run_mq_bot(args.bot_name)


def cli_start_bots():
    """
    Entry Point to start bots from a Console Script
    """
    from chatbot_core.utils.bot_utils import SERVER, start_bots
    log_deprecation("This CLI command is deprecated", "3.0.0")

    parser = argparse.ArgumentParser(description="Start some chatbots")
    parser.add_argument("--domain", dest="domain", default="chatbotsforum.org",
                        help="Domain to connect to "
                             "(default: chatbotsforum.org)", type=str)
    parser.add_argument("--dir", dest="bot_dir",
                        help="Path to chatbots (default: ./)", type=str)
    parser.add_argument("--bot", dest="bot_name",
                        help="Optional bot name to run a single bot only",
                        type=str)
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
                        help="comma separated list of bots to run", type=str)
    parser.add_argument("--exclude", dest="exclude",
                        help="comma separated list of bots to exclude "
                             "from running", type=str)
    parser.add_argument("--handle-restart", dest="handle_restart",
                        default=False,
                        help="True to handle server emit to restart bots",
                        type=bool)
    args = parser.parse_args()

    if args.debug:
        LOG.set_level("DEBUG")

    if args.exclude:
        excluded_bots = [name.strip() for name in args.exclude.split(",")]
    else:
        excluded_bots = None
    LOG.debug(args)
    start_bots(args.domain, args.bot_dir, args.username, args.password,
               args.server, args.cred_file, args.bot_name,
               excluded_bots, args.handle_restart)


def cli_stop_bots():
    """
    Stops all start-klat-bot instances
    """
    from time import sleep
    log_deprecation("This CLI command is deprecated", "3.0.0")

    parser = argparse.ArgumentParser(description="Stop some chatbots")
    parser.add_argument("--server", dest="server", default="",
                        help=f"Klat server (default: None)", type=str)
    args = parser.parse_args()
    if args.server:
        server_to_stop = args.server
    else:
        server_to_stop = None
    import psutil

    procs = {p.pid: p.info for p in psutil.process_iter(['name'])}
    for pid, name in procs.items():
        if name.get("name") == "start-klat-bots" and \
                (not server_to_stop or f"--server={server_to_stop}" in
                 psutil.Process(pid).cmdline()):
            LOG.info(f"Terminating {pid}")
            psutil.Process(pid).terminate()
            sleep(1)
            if psutil.pid_exists(pid) and psutil.Process(pid).is_running():
                LOG.error(f"Process {pid} not terminated!!")
                psutil.Process(pid).kill()


def cli_start_prompter():
    """
    Entry Point to start a prompter bot
    """
    log_deprecation("This CLI command is deprecated", "3.0.0")

    from chatbot_core.utils.bot_utils import SERVER, start_bots
    parser = argparse.ArgumentParser(description="Start a prompter chatbot")
    parser.add_argument("--bot", dest="bot_name",
                        help="Optional bot name to run a single bot only", type=str)
    parser.add_argument("--dir", dest="bot_dir",
                        help="Path to chatbots (default: ./)", type=str)
    parser.add_argument("--username", dest="username",
                        help="Klat username for a single bot", type=str)
    parser.add_argument("--password", dest="password",
                        help="Klat password for a single bot", type=str)
    parser.add_argument("--server", dest="server", default=SERVER,
                        help=f"Klat server (default: {SERVER})", type=str)
    parser.add_argument("--debug", dest="debug", action='store_true',
                        help="Enable more verbose log output")
    parser.add_argument("--handle-restart", dest="handle_restart", default=False,
                        help="True to handle server emit to restart bots", type=bool)
    args = parser.parse_args()

    if args.debug:
        LOG.level = "DEBUG"
    LOG.debug(args)
    start_bots("chatbotsforum.org", args.bot_dir, args.username, args.password,
               args.server, None, args.bot_name, None, args.handle_restart,
               True)


def cli_debug_bots():
    """
    Debug bots in the passed directory
    :param bot_dir: directory containing the bot to test
    """
    import sys
    from chatbot_core.utils.bot_utils import debug_bots

    log_deprecation("Use `chatbots debug-bots`", "3.0.0")

    bot_dir = os.getcwd()
    # Try handling passed directory
    if len(sys.argv) > 1:
        arg_dir = os.path.expanduser(sys.argv[1])
        bot_dir = arg_dir if os.path.exists(arg_dir) else bot_dir

    debug_bots(bot_dir)

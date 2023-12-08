# Chatbot Core
Bots using this framework connect to the Klat server and respond to user shouts. Bots will respond individually,
like any other user in the conversation.

## Getting Started

### Running in Colab
Configured environment and implemented code can be run from Google Colab
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/1gdFiHYMYjAzZGQPEepfpv4LNzEoEHGx2?usp=sharing)

 
### Installation
To utilize this repository for creating your own chat bots, install this package via pip and then extend the `ChatBot` or
`NeonBot` class to build your own chat bot (see the [Examples below](#python-examples)).

You can install this package with the following command:

`pip install neon-chatbot-core`

*Note*: It is recommended to install this to a virtual environment to avoid conflicts with package versions and commandline 
entry points. Most IDE's (i.e. [PyCharm](https://www.jetbrains.com/pycharm/)) handle this for individual projects.

### Configuration

#### Bot-specific configuration
Configuration for chatbots should be defined in `~/.config/neon/chatbots.yaml`
by default. Chatbots may be configured as:
```yaml
chatbots:
  <bot_id>: {}
```
> For Klat v1, `bot_id` is the `username` the bot connects as, for MQ connected
> bots, `bot_id` is the MQ `service_name`.

Any bot-specific configuration will be accessible as `self.bot_config`. For Klat
v1 connections, `password` should be specified in the `chatbots`
config section.

#### MQ Connection configuration
For v2 bots, MQ connections must also be configured. This should be completed in
the same `~/.config/neon/chatbots.yaml` file as the bot-specific config.

```yaml
MQ:
  server: mq.neonaiservices.com
  port: 5672
  users:
    <bot_id>:
      user: neon_bot_submind
      password: <MQ user `neon_bot_submind`'s password>
```

#### SocketIO Connection configuration
For v1 bots, SIO connections may be configured in `~/.config/neon/chatbots.yaml`:
```yaml
socket_io:
  server: 2222.us
  port: 8888
```

### Organizing your bots
It is recommended to create a module for each of your bots. You should use subdirectories, each containing `__init__.py`
that includes your `ChatBot` as well as any supporting configuration files, etc. You may also organize this as a
directory of .py files that each contain a bot (these bots cannot be managed with the [utilities](#commandline-utilities)
included with this package). Below are example file structures for each of these cases.

```
my_bots
|
|--venv
|--alice
|  |--aiml
|  |  └--...
|  └--__init__.py
|--ELIZA
|  └--__init__.py
└--ima
   └--__init__.py
```

```
my_bots
|
|--venv
└--my_bot.py
```

### Legacy Klat.com Credentials
Bots should be able to login to [klat.com](https://klat.com); a YAML file containing credentials for each bot can be used
to save usernames and passwords for each bot. Each bot module should have a key matching the module name, a `username`,
and a `password`.

```yaml
ALICE:
  username: alice
  password: AliceKlatPassword
kbot:
  username: kbot
  password: kBotKlatPassword
```

### Commandline Utilities
There are commandline utilities provided to test and run bots you create. The examples for these utilities assumes you
have your bots in a directory named `my_bots` as outlined [above](#organizing-your-bots).

#### debug-klat-bots
From a terminal that has sourced your virtual environment, you can run the following command to test any one of your bots:

```shell script
debug-klat-bots "/path/to/my_bots"
```
*Note:* You may omit the path argument if your terminal is in the same directory as your bots.

#### start-klat-bots
From a terminal that has sourced your virtual environment, you can run the following command to run all of your bots:

```shell script
start-klat-bots --domain chatbotsforum.org --bots "/path/to/my_bots" --credentials "/path/to/credentials.yml"
```
*Note:* Call start-klat-bots -h for detailed help explaining each of the parameters

## Generating Responses
### Basic Bot
Basic bots override `self.ask_chatbot` to generate a response. Bots have access to the shout, the user who originated 
the shout, and the timestamp of the shout. Any means may be used to generate and return a response via 
the `self.propose_response` method. If no response can be generated, return the input to use a random response from 
`self.fallback_responses`.

### Script Bot
Bots extending the `NeonBot` class operate by passing user shouts to a Neon Script and returning those responses.
`NeonBot` init takes the name of the script to run (`"SCRIPT_NAME"` in the example below), 
as well as the messagebus configuration for the `NeonCore` instance on which to run the script.

## Testing
### Basic Bot
The response generation of a bot should be tested individually before connecting it to the Klat network. This can be 
accomplished by passing `on_server=False` and then calling `ask_chatbot` directly.
The [Python examples below](#python-examples) show how you can do this in the file containing your ChatBot.

### Script Bot
A script should be tested separately from the bot before creating a `NeonBot`. More information about developing scripts
can be found on [the Neon Scripts Repository](https://github.com/NeonGeckoCom/neon-scripts). After the script functions 
as expected, it can be used to extend a `NeonBot`.

## Proctored Conversations
Proctored conversations on the Klat network are conversations where multiple *subminds* (bots and users) may collaborate to
respond to incoming prompts. These conversations use a *Proctor* to pose questions and manage the voting and selection 
process among the multiple *subminds*. The following additional methods should be implemented to fully support 
participating in proctored conversations. It is not explicitly required to implement all methods, but doing so is recommended.

### ask_chatbot
Override `ask_chatbot` to propose generated response from bot to conversation. `shout` - question from user.

### ask_discusser
Override `ask_discusser` to provide some discussion of the proposed responses after all *subminds* have had an opportunity
to respond. Discussion can be anything, but generally is an endoresement of one of the proposed responses (a bot may 
endorse their own response).

### on_discussion
Override `on_discussion` to handle discussion responses from other *subminds*. A bot may use these responses to influence 
which bot/response they vote for, or possibly to affect their discussion of the next prompt.

### ask_appraiser
Override `ask_appraiser` to select a bot to vote for (a bot may not vote for themself). Any means may be used to select 
a bot; `options` provides a dictionary of valid names to vote for and their responses.

### on_login
Override `on_login` to execute any initialization after logging in or after connection if no username/password.

### on_vote
Override `on_vote` in any bot to handle counting votes. Proctors use this to select a response.

### on_discussion
Override `on_discussion` in any bot to handle discussion from other subminds. This may inform voting for the current prompt.

### on_proposed_response
Override `on_proposed_response` in Proctor to check when to notify bots to vote.

### on_selection
Override `on_selection` in any bot to handle a proctor selection of a response.

### at_chatbot
Override `at_chatbot` in subminds to handle an incoming shout that is directed at this bot. Defaults to ask_chatbot.

### ask_proctor
Override `ask_proctor` in proctor to handle a new prompt to queue.

### ask_history
Override `ask_history` in scorekeepers to handle an incoming request for the selection history.

## Python Examples
### Standard Bot
```python
from chatbot_core import ChatBot, start_socket
import random

class MyBot(ChatBot):
    def __init__(self, socket, domain, user, password, on_server=True):
        super(MyBot, self).__init__(socket, domain, user, password)
        self.on_server = on_server
        self.last_search = None

    def ask_chatbot(self, user, shout, timestamp):
        """
        Handles an incoming shout into the current conversation
        :param user: user associated with shout
        :param shout: text shouted by user
        :param timestamp: formatted timestamp of shout
        """
        resp = f""  # Generate some response here
        if self.on_server:
            self.propose_response(resp)
        else:
            return resp

    def ask_appraiser(self, options):
        """
        Selects one of the responses to a prompt and casts a vote in the conversation
        :param options: proposed responses (botname: response)
        """
        selection = random.choice(list(options.keys()))
        self.vote_response(selection)

    def ask_discusser(self, options):
        """
        Provides one discussion response based on the given options
        :param options: proposed responses (botname: response)
        """
        selection = list(options.keys())[0]  # Note that this example doesn't match the voted choice
        self.discuss_response(f"I like {selection}.")

    def on_discussion(self, user: str, shout: str):
        """
        Handle discussion from other subminds. This may inform voting for the current prompt
        :param user: user associated with shout
        :param shout: shout to be considered
        """
        pass

    def on_login(self):
        """
        Do any initialization after logging in
        """
        pass

if __name__ == "__main__":
    # Testing
    bot = MyBot(start_socket("2222.us", 8888), f"chatbotsforum.org", None, None, False)
    while True:
        try:
            utterance = input('[In]: ')
            response = bot.ask_chatbot(f'', utterance, f'')
            print(f'[Out]: {response}')
        except KeyboardInterrupt:
            break
        except EOFError:
            break
    # Running on the forum
    MyBot(start_socket("2222.us", 8888), f"chatbotsforum.org", None, None, True)
    while True:
        pass
```
### Script Bot
```python
from chatbot_core import NeonBot
from chatbot_core import start_socket

class ScriptBot(NeonBot):
    def __init__(self, socket, domain, user, password, on_server=True):
        super(ScriptBot, self).__init__(socket, domain, user, password, on_server, "SCRIPT NAME", {"host": "CORE_ADDR",
                                                                                                   "port": 8181,
                                                                                                   "ssl": False,
                                                                                                   "route": "/core"})
        self.on_server = on_server

    def ask_appraiser(self, options):
        """
        Selects one of the responses to a prompt and casts a vote in the conversation
        :param options: proposed responses (botname: response)
        """
        selection = list(options.keys())[0]
        self.vote_response(selection)

    def ask_discusser(self, options):
        """
        Provides one discussion response based on the given options
        :param options: proposed responses (botname: response)
        """
        selection = list(options.keys())[0]
        self.discuss_response(f"I like {selection}.")

    def on_discussion(self, user: str, shout: str):
        """
        Handle discussion from other subminds. This may inform voting for the current prompt
        :param user: user associated with shout
        :param shout: shout to be considered
        """
        pass
if __name__ == "__main__":
    # Testing
    bot = ScriptBot(start_socket("2222.us", 8888), f"chatbotsforum.org", None, None, False)
    while True:
        try:
            utterance = input('[In]: ')
            response = bot.ask_chatbot(f'', utterance, f'')
            print(f'[Out]: {response}')
        except KeyboardInterrupt:
            break
        except EOFError:
            break
        # Running on the forum
    ScriptBot(start_socket("2222.us", 8888), f"chatbotsforum.org", None, None, True)
    while True:
        pass
```

## Helper functions
### Grammar check
In order to apply quick validation on output of function consider using `grammar_check`,
Sample Usage:
```python
from chatbot_core import grammar_check
@grammar_check
def ask_chatbot(self, user: str, shout: str, timestamp: str) -> str:
    return shout
```
Kernel of this function made with the help of [autocorrect](https://github.com/fsondej/autocorrect)

### Find closest opinion
Apply `find_closest_answer` to provide some known algorithms for closest opinions finding, 
Sample Usage:
```python
from chatbot_core import find_closest_answer

def ask_appraiser(self, options: dict) -> str:
    # Let's consider storing response for current prompt in self.response variable
    closest_opinion = find_closest_answer(algorithm='random',sentence=self.response,options=options)
    for bot in options.keys():
        if options[bot] == closest_opinion:
            return f'I really like {bot} opinion!'
    return 'I did not found any interesting answer here...'
```
#### Algorithm Table


|    Algorithm Name    |                                                                                          Description                                                                                         |                                   When to use?                                   |
|:--------------------:|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------:|:--------------------------------------------------------------------------------:|
|        random        |                                                                                   Picks response by random                                                                                   |                          When matters speed over result                          |
|      bleu score      |                                                          Calculates precision using [n-gramms](https://en.wikipedia.org/wiki/N-gram)                                                         |                         When sentences have similar shape                        |
| levenshtein distance | Calculates precision by measuring distance between words.  | When each word separately matters more than semantical meaning of the sentence.  |

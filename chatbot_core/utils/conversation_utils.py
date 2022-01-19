from itertools import cycle

from chatbot_core import ConversationState


def create_conversation_cycle() -> cycle:
    """Cycle through conversation states"""
    return cycle([ConversationState.RESP,
                  ConversationState.DISC,
                  ConversationState.VOTE,
                  ConversationState.PICK,
                  ConversationState.IDLE])

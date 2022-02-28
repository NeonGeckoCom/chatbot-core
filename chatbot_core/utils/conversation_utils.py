from itertools import cycle


def create_conversation_cycle() -> cycle:
    """Cycle through conversation states"""
    from chatbot_core.utils import ConversationState

    return cycle([ConversationState.RESP,
                  ConversationState.DISC,
                  ConversationState.VOTE,
                  ConversationState.PICK,
                  ConversationState.IDLE])

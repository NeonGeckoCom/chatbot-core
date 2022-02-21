from enum import IntEnum, Enum


class ConversationControls:
    RESP = " asks us to consider:"
    DISC = "Please Discuss"
    VOTE = "Voting on the response to "
    PICK = "Tallying the votes for the responses to "
    NEXT = "I'm ready for the next prompt."
    HIST = "history"
    WAIT = " may respond to the next prompt."


class ConversationState(IntEnum):
    IDLE = 0  # No active prompt
    RESP = 1  # Gathering responses to prompt
    DISC = 2  # Discussing responses
    VOTE = 3  # Voting on responses
    PICK = 4  # Proctor will select response
    WAIT = 5  # Bot is waiting for the proctor to ask them to respond (not participating)


class BotTypes:
    PROCTOR = 'proctor'
    SUBMIND = 'submind'
    OBSERVER = 'observer'


CONVERSATION_STATE_ANNOUNCEMENTS = {
    ConversationState.RESP: 'Accepting responses from subminds ({interval} seconds)',
    ConversationState.DISC: 'Discussing responses from subminds ({interval} seconds)',
    ConversationState.VOTE: 'Voting for candidate responses ({interval} seconds)',
    ConversationState.PICK: 'Selecting a winner among participants'
}

"""Errors raised when display history cannot be saved or loaded."""


class ConversationHistoryError(Exception):
    """Base class for conversation-history errors translated at the HTTP boundary."""


class ConversationHistoryDatabaseError(ConversationHistoryError):
    """A database operation for conversation history failed."""

    def __init__(self, operation: str) -> None:
        """Record which persistence action failed."""
        self.operation = operation
        super().__init__(f"Conversation history {operation} failed")


class ConversationNotFoundError(ConversationHistoryError):
    """The requested conversation does not exist."""

    def __init__(self, conversation_id: str) -> None:
        """Store the missing conversation id."""
        self.conversation_id = conversation_id
        super().__init__(f"Conversation {conversation_id} not found")


class ConversationAccessDeniedError(ConversationHistoryError):
    """The user may not read this conversation."""

    def __init__(self, conversation_id: str, user_id: str) -> None:
        """Store the conversation and user involved."""
        self.conversation_id = conversation_id
        self.user_id = user_id
        super().__init__(
            f"User {user_id} may not read conversation {conversation_id}",
        )


class TurnNotFoundError(ConversationHistoryError):
    """No saved turn exists for the given response."""

    def __init__(self, response_id: str) -> None:
        """Store the missing response id."""
        self.response_id = response_id
        super().__init__(f"Turn for response {response_id} not found")


class InvalidConversationIdError(ConversationHistoryError):
    """A client-supplied conversation id is not a valid SUID."""

    def __init__(self, conversation_id: str) -> None:
        """Store the rejected id."""
        self.conversation_id = conversation_id
        super().__init__(f"Invalid conversation id: {conversation_id}")

"""Model for conversation history cache entry."""

from pydantic import BaseModel


class CacheEntry(BaseModel):
    """Model representing a cache entry.

    Attributes:
        query: The query string
        response: The response string
        provider: Provider identification
        model: Model identification
    """

    query: str
    response: str
    provider: str
    model: str


class ConversationData(BaseModel):
    """Model representing conversation data returned by cache list operations.

    Attributes:
        conversation_id: The conversation ID
        topic_summary: The topic summary for the conversation (can be None)
        last_message_timestamp: The timestamp of the last message in the conversation
    """

    conversation_id: str
    topic_summary: str | None
    last_message_timestamp: float

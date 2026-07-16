"""Conversation resolution result model for the OpenAI-compatible responses endpoint."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from models.database.conversations import UserConversation


class ResponsesConversationContext(BaseModel):
    """Result of resolving conversation context for the responses endpoint.

    Holds the conversation ID to use for the LLM, the optional user conversation
    record, and the resolved generate_topic_summary flag. Caller assigns these
    to the request in outer scope instead of mutating the request inside the
    resolver.

    Attributes:
        conversation: Conversation ID in llama-stack format to use for the request.
        user_conversation: Resolved user conversation record, or None for new ones.
        generate_topic_summary: Resolved value for request.generate_topic_summary.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    conversation: str = Field(description="Conversation ID in llama-stack format")
    user_conversation: Optional[UserConversation] = Field(
        default=None,
        description="Resolved user conversation record, or None for new conversations",
    )
    generate_topic_summary: bool = Field(
        description="Resolved value for request.generate_topic_summary",
    )

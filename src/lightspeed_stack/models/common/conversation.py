"""Conversation list rows, metadata, and simplified turn/message shapes for APIs."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from models.common.turn_summary import (
    ReferencedDocument,
    ToolCallSummary,
    ToolResultSummary,
)


class ConversationData(BaseModel):
    """Model representing conversation data returned by cache list operations.

    Attributes:
        conversation_id: The conversation ID
        topic_summary: The topic summary for the conversation (can be None)
        last_message_timestamp: The timestamp of the last message in the conversation
    """

    conversation_id: str
    topic_summary: Optional[str]
    last_message_timestamp: float


class ConversationDetails(BaseModel):
    """Model representing the details of a user conversation.

    Attributes:
        conversation_id: The conversation ID (UUID).
        created_at: When the conversation was created.
        last_message_at: When the last message was sent.
        message_count: Number of user messages in the conversation.
        last_used_model: The last model used for the conversation.
        last_used_provider: The provider of the last used model.
        topic_summary: The topic summary for the conversation.

    Example:
        ```python
        conversation = ConversationDetails(
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
            created_at="2024-01-01T00:00:00Z",
            last_message_at="2024-01-01T00:05:00Z",
            message_count=5,
            last_used_model="gemini/gemini-2.0-flash",
            last_used_provider="gemini",
            topic_summary="Openshift Microservices Deployment Strategies",
        )
        ```
    """

    conversation_id: str = Field(
        ...,
        description="Conversation ID (UUID)",
        examples=["c5260aec-4d82-4370-9fdf-05cf908b3f16"],
    )

    created_at: Optional[str] = Field(
        None,
        description="When the conversation was created",
        examples=["2024-01-01T01:00:00Z"],
    )

    last_message_at: Optional[str] = Field(
        None,
        description="When the last message was sent",
        examples=["2024-01-01T01:00:00Z"],
    )

    message_count: Optional[int] = Field(
        None,
        description="Number of user messages in the conversation",
        examples=[42],
    )

    last_used_model: Optional[str] = Field(
        None,
        description="Identification of the last model used for the conversation",
        examples=["gpt-4-turbo", "gpt-3.5-turbo-0125"],
    )

    last_used_provider: Optional[str] = Field(
        None,
        description="Identification of the last provider used for the conversation",
        examples=["openai", "gemini"],
    )

    topic_summary: Optional[str] = Field(
        None,
        description="Topic summary for the conversation",
        examples=["Openshift Microservices Deployment Strategies"],
    )


class Message(BaseModel):
    """Model representing a message in a conversation turn.

    Attributes:
        content: The message content.
        type: The type of message.
        referenced_documents: Optional list of documents referenced in an assistant response.
    """

    content: str = Field(
        ...,
        description="The message content",
        examples=["Hello, how can I help you?"],
    )
    type: Literal["user", "assistant", "system", "developer"] = Field(
        ...,
        description="The type of message",
        examples=["user", "assistant", "system", "developer"],
    )
    referenced_documents: Optional[list[ReferencedDocument]] = Field(
        None,
        description="List of documents referenced in the response (assistant messages only)",
    )


class ConversationTurn(BaseModel):
    """Model representing a single conversation turn.

    Attributes:
        messages: List of messages in this turn.
        tool_calls: List of tool calls made in this turn.
        tool_results: List of tool results from this turn.
        provider: Provider identifier used for this turn.
        model: Model identifier used for this turn.
        started_at: ISO 8601 timestamp when the turn started.
        completed_at: ISO 8601 timestamp when the turn completed.
    """

    messages: list[Message] = Field(
        default_factory=list,
        description="List of messages in this turn",
    )
    tool_calls: list[ToolCallSummary] = Field(
        default_factory=list,
        description="List of tool calls made in this turn",
    )
    tool_results: list[ToolResultSummary] = Field(
        default_factory=list,
        description="List of tool results from this turn",
    )
    provider: str = Field(
        ...,
        description="Provider identifier used for this turn",
        examples=["openai"],
    )
    model: str = Field(
        ...,
        description="Model identifier used for this turn",
        examples=["gpt-4o-mini"],
    )
    started_at: str = Field(
        ...,
        description="ISO 8601 timestamp when the turn started",
        examples=["2024-01-01T00:01:00Z"],
    )
    completed_at: str = Field(
        ...,
        description="ISO 8601 timestamp when the turn completed",
        examples=["2024-01-01T00:01:05Z"],
    )

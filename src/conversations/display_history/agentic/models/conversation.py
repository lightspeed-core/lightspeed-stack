"""Conversation envelope for v3 display history."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from conversations.display_history.agentic.models.agent_turn import AgentTurn


class ConversationMetadata(BaseModel):
    """Shared metadata for get and list conversation responses."""

    model_config = ConfigDict(extra="ignore")

    conversation_id: str = Field(
        ...,
        description="Conversation ID (UUID)",
        examples=["c5260aec-4d82-4370-9fdf-05cf908b3f16"],
    )
    created_at: str = Field(
        ...,
        description="When the conversation was created",
        examples=["2024-01-01T01:00:00Z"],
    )
    last_turn_at: Optional[str] = Field(
        default=None,
        description="When the most recent agent run completed or paused",
        examples=["2024-01-01T01:05:00Z"],
    )
    turn_count: int = Field(
        default=0,
        description="Number of agent runs in the conversation",
        ge=0,
        examples=[3],
    )
    last_used_model: Optional[str] = Field(
        default=None,
        description="Identification of the last model used",
        examples=["gpt-4-turbo"],
    )
    last_used_provider: Optional[str] = Field(
        default=None,
        description="Identification of the last provider used",
        examples=["openai"],
    )
    topic_summary: Optional[str] = Field(
        default=None,
        description="Topic summary for the conversation",
        examples=["OpenShift deployment strategies"],
    )


class Conversation(ConversationMetadata):
    """Full conversation including ordered display history."""

    chat_history: list[AgentTurn] = Field(
        default_factory=list,
        description="Ordered agent runs for the conversation",
    )

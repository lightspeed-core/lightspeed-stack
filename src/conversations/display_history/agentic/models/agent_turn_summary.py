"""Agent run fields persisted on the agentic turn row."""

from typing import Optional

from pydantic import BaseModel, Field

from conversations.display_history.agentic.models.turn_items import TurnItem
from conversations.display_history.agentic.models.types import (
    AgentTurnStatus,
    ContextStatus,
)
from models.common.turn_summary import ReferencedDocument


class AgentTurnSummary(BaseModel):
    """Persisted agent-run payload for display history.

    Conversation id, provider, model, and timestamps live on parent rows.
    The public agent turn shown to clients joins those envelopes with this
    summary.

    """

    status: AgentTurnStatus = Field(..., description="Run lifecycle status")
    agent: Optional[str] = Field(
        default=None,
        description="Optional agent identifier; reserved for future use",
    )
    context_status: ContextStatus = Field(
        default="full",
        description="Whether agent history for this run was full or compacted",
    )
    input_tokens: int = Field(
        default=0,
        description="Tokens sent to the model during the run",
        ge=0,
    )
    output_tokens: int = Field(
        default=0,
        description="Tokens received from the model during the run",
        ge=0,
    )
    referenced_documents: list[ReferencedDocument] = Field(
        default_factory=list,
        description="Deduplicated citations for the turn",
    )
    input: list[TurnItem] = Field(
        default_factory=list,
        description="Ordered items that started the run",
    )
    output: list[TurnItem] = Field(
        default_factory=list,
        description="Ordered items the run produced",
    )

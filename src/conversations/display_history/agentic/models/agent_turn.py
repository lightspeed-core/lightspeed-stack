"""Single agent run projected into display history."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from conversations.display_history.agentic.models.turn_items import TurnItem
from conversations.display_history.agentic.models.types import (
    AgentTurnStatus,
    ContextStatus,
)
from models.common.turn_summary import ReferencedDocument


class TurnUsage(BaseModel):
    """Aggregated token usage for one agent run."""

    model_config = ConfigDict(extra="ignore")

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


class AgentTurn(BaseModel):
    """One agent run in the public conversation timeline.

    A turn is one PAI Agent.run (same identity as Responses response.id when
    that path created the run). The timeline order within a turn is input
    followed by output.
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Run identity (run_id / response id)")
    status: AgentTurnStatus = Field(
        ...,
        description="Run lifecycle status",
    )
    agent: Optional[str] = Field(
        default=None,
        description="Optional agent identifier; reserved for future use",
    )
    provider: str = Field(..., description="Inference provider used for the run")
    model: str = Field(..., description="Inference model used for the run")
    started_at: str = Field(
        ...,
        description="ISO 8601 timestamp when the run started",
        examples=["2024-01-01T00:01:00Z"],
    )
    completed_at: str = Field(
        ...,
        description="ISO 8601 timestamp when the run completed or paused",
        examples=["2024-01-01T00:01:05Z"],
    )
    context_status: ContextStatus = Field(
        ...,
        description="Whether agent history for this run was full or compacted",
    )
    usage: TurnUsage = Field(
        default_factory=TurnUsage,
        description="Aggregated token usage for the run",
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

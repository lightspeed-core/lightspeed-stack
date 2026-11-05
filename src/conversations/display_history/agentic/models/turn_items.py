"""Discriminated turn items for agentic display history."""

from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from conversations.display_history.agentic.models.content import MessageContent
from conversations.display_history.agentic.models.types import (
    MessageRole,
    SourcesOrigin,
    ToolResultBody,
    ToolResultStatus,
    ToolsetKind,
)


class TurnItemBase(BaseModel):
    """Shared fields for every item in input or output.

    Subclasses declare kind as a literal discriminator; it is not declared on
    the base class so narrowed literals type-check under pyright.
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Stable identifier for this turn item")


class ToolsetInfo(BaseModel):
    """Classifies which tool family a call or result belongs to for display."""

    model_config = ConfigDict(extra="ignore")

    type: ToolsetKind = Field(
        ...,
        description=("Tool family: function, mcp, file_search, web_search, or skills"),
    )
    label: Optional[str] = Field(
        default=None,
        description="Human-readable toolset label when applicable",
        examples=["filesystem"],
    )


class SourceChunk(BaseModel):
    """Retrieval chunk attached to a sources turn item."""

    model_config = ConfigDict(extra="ignore")

    content: str = Field(..., description="Chunk text")
    source: Optional[str] = Field(
        default=None,
        description="Knowledge source or index name",
    )
    score: Optional[float] = Field(default=None, description="Relevance score")
    attributes: Optional[dict[str, Any]] = Field(
        default=None,
        description="Document metadata from the provider",
    )


class MessageTurnItem(TurnItemBase):
    """User or assistant multimodal message."""

    kind: Literal["message"] = "message"
    role: MessageRole = Field(..., description="Message author")
    content: MessageContent = Field(
        ...,
        description="Ordered multimodal message parts",
    )


class ToolCallTurnItem(TurnItemBase):
    """Tool invocation produced during a run."""

    kind: Literal["tool_call"] = "tool_call"
    call_id: str = Field(..., description="Tool call identifier")
    name: str = Field(..., description="Tool name")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments passed to the tool",
    )
    toolset: ToolsetInfo = Field(
        ...,
        description="Tool family classification for this call",
    )


class ToolResultTurnItem(TurnItemBase):
    """Outcome of a tool call."""

    kind: Literal["tool_result"] = "tool_result"
    call_id: str = Field(
        ...,
        description="Matches the corresponding tool_call call_id",
    )
    name: Optional[str] = Field(
        default=None,
        description="Tool name when useful without the paired tool_call item",
    )
    status: ToolResultStatus = Field(
        ...,
        description=(
            "success: normal completion; failed: execution error; "
            "denied: blocked or not recorded (guardrail, etc.); "
            "interrupted: run stopped before tool finished"
        ),
    )
    content: ToolResultBody = Field(
        ...,
        description="Tool outcome: UTF-8 text or structured JSON (object or array)",
    )
    toolset: ToolsetInfo = Field(
        ...,
        description="Tool family classification for this result",
    )


class SourcesTurnItem(TurnItemBase):
    """Retrieval evidence for the turn (automatic RAG or tool-backed)."""

    kind: Literal["sources"] = "sources"
    origin: SourcesOrigin = Field(
        ...,
        description="Whether evidence came from automatic RAG or a tool",
    )
    chunks: list[SourceChunk] = Field(
        default_factory=list,
        description="Retrieved chunks for this item",
    )


class ReasoningTurnItem(TurnItemBase):
    """Optional reasoning content exposed for the run."""

    kind: Literal["reasoning"] = "reasoning"
    content: str = Field(..., description="Reasoning text")


class ApprovalRequestTurnItem(TurnItemBase):
    """Human-in-the-loop approval request (typically in output)."""

    kind: Literal["approval_request"] = "approval_request"
    call_id: str = Field(..., description="Related tool call identifier")
    name: str = Field(
        ...,
        description="Tool name for the invocation pending approval",
    )
    arguments: Optional[dict[str, Any]] = Field(
        default=None,
        description="Arguments for the invocation pending approval",
    )
    toolset: ToolsetInfo = Field(
        ...,
        description="Tool family classification for the pending invocation",
    )


class ApprovalResultTurnItem(TurnItemBase):
    """Approval decision when resuming a deferred run (typically in input)."""

    kind: Literal["approval_result"] = "approval_result"
    call_id: str = Field(..., description="Related tool call identifier")
    approved: bool = Field(..., description="Whether the action was approved")
    reason: Optional[str] = Field(
        default=None,
        description="Optional explanation for the decision",
    )


TurnItem = Annotated[
    MessageTurnItem
    | ToolCallTurnItem
    | ToolResultTurnItem
    | SourcesTurnItem
    | ReasoningTurnItem
    | ApprovalRequestTurnItem
    | ApprovalResultTurnItem,
    Field(discriminator="kind"),
]

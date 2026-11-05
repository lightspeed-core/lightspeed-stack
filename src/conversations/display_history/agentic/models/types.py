"""Literal types for the agentic display-history conversation contract."""

from typing import Any, Literal

type ToolResultBody = str | dict[str, Any] | list[Any]
"""Tool output for display: plain text, a JSON object, or a JSON array."""

AgentTurnStatus = Literal["completed", "interrupted", "failed", "awaiting_input"]
"""Lifecycle of a single agent run projected into display history."""

ContextStatus = Literal["full", "compacted"]
"""Whether agent history was compacted before this run (see compaction migration)."""

SourcesOrigin = Literal["auto", "tool"]
"""Whether retrieval evidence came from automatic inline RAG or a tool."""

MessageRole = Literal["user", "assistant"]
"""Speaker for a message turn item."""

ToolResultStatus = Literal["success", "failed", "denied", "interrupted"]
"""Maps to pydantic_ai ToolReturnPart.outcome for tool return parts."""

TurnItemKind = Literal[
    "message",
    "tool_call",
    "tool_result",
    "sources",
    "reasoning",
    "approval_request",
    "approval_result",
]
"""Discriminator for ordered items in an agent turn's input or output."""

ToolsetKind = Literal[
    "function",
    "mcp",
    "file_search",
    "web_search",
    "skills",
]
"""Tool family for display (LCS/PAI surfaces: function_call, mcp_call, file_search_call)."""

"""Public ids for conversations, agent runs, and display turn items."""

from __future__ import annotations

import uuid
from typing import Final, Literal

type IdResource = Literal[
    "conversation",
    "run",
    "message",
    "tool_call",
    "tool_result",
    "reasoning",
    "sources",
]

_CONVERSATION_PREFIX: Final[str] = "conv_"

_RESOURCE_PREFIXES: Final[dict[IdResource, str]] = {
    "conversation": _CONVERSATION_PREFIX,
    "run": "resp_",
    "message": "msg_",
    "tool_call": "tc_",
    "tool_result": "tr_",
    "reasoning": "rsn_",
    "sources": "src_",
}


def new_id(resource: IdResource) -> str:
    """Generate a new client-facing id.

    Args:
        resource: Kind of resource the id identifies.

    Returns:
        A new prefixed UUID for that resource.

    """
    return f"{_RESOURCE_PREFIXES[resource]}{uuid.uuid4()}"


def strip_conversation_prefix(conversation_id: str) -> str:
    """Remove the conversation prefix when present."""
    return conversation_id.removeprefix(_CONVERSATION_PREFIX)


def with_conversation_prefix(conversation_id: str) -> str:
    """Add the conversation prefix when missing."""
    return f"{_CONVERSATION_PREFIX}{conversation_id.removeprefix(_CONVERSATION_PREFIX)}"

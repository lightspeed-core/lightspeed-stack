"""Public ids for conversations and responses."""

from __future__ import annotations

import uuid
from typing import Final

_CONVERSATION_PREFIX: Final[str] = "conv_"
_RUN_PREFIX: Final[str] = "resp_"


def new_conversation_id() -> str:
    """Generate a new conversation id for the client."""
    return f"{_CONVERSATION_PREFIX}{uuid.uuid4()}"


def new_run_id() -> str:
    """Generate a new response id for the client."""
    return f"{_RUN_PREFIX}{uuid.uuid4()}"


def strip_conversation_prefix(conversation_id: str) -> str:
    """Remove the conversation prefix when present."""
    return conversation_id.removeprefix(_CONVERSATION_PREFIX)


def with_conversation_prefix(conversation_id: str) -> str:
    """Add the conversation prefix when missing."""
    return f"{_CONVERSATION_PREFIX}{conversation_id.removeprefix(_CONVERSATION_PREFIX)}"

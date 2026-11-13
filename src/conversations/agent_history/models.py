"""Data for resolving the next agent run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pydantic_ai.messages import ModelMessage

from conversations.agent_history.ids import (
    new_conversation_id,
    new_run_id,
    with_conversation_prefix,
)


@dataclass(frozen=True)
class RunResolutionParams:
    """Continuation inputs from the client request (without the step store)."""

    user_id: str
    others_allowed: bool
    store: bool = True
    conversation_id: Optional[str] = None
    previous_response_id: Optional[str] = None


@dataclass(frozen=True)
class ResolvedAgentRun:
    """Ids and prior messages for one agent invocation."""

    run_id: str
    conversation_id: Optional[str]
    message_history: list[ModelMessage]

    @classmethod
    def stateless(cls) -> ResolvedAgentRun:
        """Start a one-off response with no saved conversation."""
        return cls(run_id=new_run_id(), conversation_id=None, message_history=[])

    @classmethod
    def new_conversation(
        cls,
        *,
        message_history: Optional[list[ModelMessage]] = None,
    ) -> ResolvedAgentRun:
        """Start a new saved conversation and response."""
        return cls(
            run_id=new_run_id(),
            conversation_id=new_conversation_id(),
            message_history=message_history or [],
        )

    @classmethod
    def continue_conversation(
        cls,
        *,
        conversation_id: str,
        message_history: list[ModelMessage],
    ) -> ResolvedAgentRun:
        """Keep the same conversation and start a new response."""
        return cls(
            run_id=new_run_id(),
            conversation_id=with_conversation_prefix(conversation_id),
            message_history=message_history,
        )

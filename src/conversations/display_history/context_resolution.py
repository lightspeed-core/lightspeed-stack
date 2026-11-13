"""Decide whether to continue or fork from saved conversation data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from conversations.display_history.access import get_user_conversation
from conversations.display_history.errors import TurnNotFoundError
from conversations.display_history.persistence.models import UserTurn
from conversations.display_history.persistence.repository.turn import (
    get_turn_by_response_id,
)
from utils.suid import normalize_conversation_id


@dataclass(frozen=True)
class ConversationContinuation:
    """Keep the same conversation for the next response."""

    conversation_id: str


@dataclass(frozen=True)
class PreviousResponseContinuation:
    """Outcome of continuing from a prior response."""

    conversation_id: str
    source_response_id: str
    fork: bool


def get_continuation_turn(previous_response_id: str) -> UserTurn:
    """Load the saved turn we are continuing from.

    Args:
        previous_response_id: Prior response from the client.

    Returns:
        The matching turn row.

    Raises:
        TurnNotFoundError: No turn exists for that response.

    """
    turn = get_turn_by_response_id(previous_response_id)
    if turn is None:
        raise TurnNotFoundError(previous_response_id)
    return turn


def is_conversation_tip(
    last_response_id: Optional[str],
    previous_response_id: str,
) -> bool:
    """Return whether the prior response is still the latest in the thread.

    Args:
        last_response_id: Latest saved response on the conversation, if any.
        previous_response_id: Response the client asked to continue from.

    Returns:
        True when continuing does not require a fork.

    """
    return last_response_id is None or last_response_id == previous_response_id


def plan_conversation_continuation(
    conversation_id: str,
    user_id: str,
    others_allowed: bool,
) -> ConversationContinuation:
    """Verify access and plan to continue a conversation by id.

    Args:
        conversation_id: Conversation from the client.
        user_id: User requesting access.
        others_allowed: Whether other users conversations are readable.

    Returns:
        Normalized conversation id to continue.

    """
    normalized = normalize_conversation_id(conversation_id)
    conversation = get_user_conversation(normalized, user_id, others_allowed)
    return ConversationContinuation(conversation_id=conversation.id)


def plan_previous_response_continuation(
    previous_response_id: str,
    user_id: str,
    others_allowed: bool,
) -> PreviousResponseContinuation:
    """Plan continue or fork from a prior response.

    Args:
        previous_response_id: Response from the client.
        user_id: User requesting access.
        others_allowed: Whether other users conversations are readable.

    Returns:
        Conversation to use, source response, and whether to fork.

    """
    turn = get_continuation_turn(previous_response_id)
    conversation = get_user_conversation(
        turn.conversation_id,
        user_id,
        others_allowed,
    )
    fork = not is_conversation_tip(
        conversation.last_response_id,
        previous_response_id,
    )
    return PreviousResponseContinuation(
        conversation_id=turn.conversation_id,
        source_response_id=previous_response_id,
        fork=fork,
    )

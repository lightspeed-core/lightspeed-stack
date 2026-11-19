"""Read and mutate display-history conversations for the v3 Conversations API."""

from __future__ import annotations

from conversations.display_history.access import (
    check_conversation_access,
    get_user_conversation,
)
from conversations.display_history.agentic.models.conversation import (
    Conversation,
    ConversationMetadata,
)
from conversations.display_history.errors import ConversationAccessDeniedError
from conversations.display_history.persistence.mapping.conversation import (
    map_conversation,
    map_conversation_metadata,
)
from conversations.display_history.persistence.repository.agentic_turn import (
    list_agentic_turns_for_conversation,
)
from conversations.display_history.persistence.repository.conversation import (
    delete_conversation as delete_conversation_row,
)
from conversations.display_history.persistence.repository.conversation import (
    list_conversations as list_conversation_rows,
)
from conversations.display_history.persistence.repository.conversation import (
    list_conversations_for_user,
    update_conversation_topic_summary,
)
from conversations.display_history.persistence.repository.turn import (
    list_turns_for_conversation,
)
from log import get_logger
from utils.suid import normalize_conversation_id

logger = get_logger(__name__)


def list_conversations(
    user_id: str,
    others_allowed: bool,
) -> list[ConversationMetadata]:
    """List conversations visible to the caller.

    Args:
        user_id: Authenticated user.
        others_allowed: When true, include other users' conversations.

    Returns:
        Conversation metadata without chat history.

    """
    rows = (
        list_conversation_rows()
        if others_allowed
        else list_conversations_for_user(user_id)
    )
    logger.info("Listed %s conversations for user %s", len(rows), user_id)
    return [map_conversation_metadata(row) for row in rows]


def get_conversation(
    conversation_id: str,
    user_id: str,
    others_allowed: bool,
) -> Conversation:
    """Load one conversation with chat history.

    Args:
        conversation_id: Conversation id; client prefix is optional.
        user_id: Authenticated user.
        others_allowed: When true, allow reading other users' conversations.

    Returns:
        Full conversation for the v3 API.

    Raises:
        ConversationAccessDeniedError: Caller may not read this conversation.
        ConversationNotFoundError: Conversation does not exist.
        DisplayHistoryDatabaseError: Database operation failed.

    """
    normalized = normalize_conversation_id(conversation_id)
    row = get_user_conversation(normalized, user_id, others_allowed)
    conversation = map_conversation(
        row,
        list_turns_for_conversation(normalized),
        list_agentic_turns_for_conversation(normalized),
    )
    logger.info(
        "Loaded conversation %s for user %s with %s turns",
        normalized,
        user_id,
        len(conversation.chat_history),
    )
    return conversation


def delete_conversation(
    conversation_id: str,
    user_id: str,
    others_allowed: bool,
) -> bool:
    """Delete a conversation when the caller is allowed.

    Missing conversations return false rather than an access error so the
    HTTP layer can match v2 delete semantics.

    Args:
        conversation_id: Conversation id; client prefix is optional.
        user_id: Authenticated user.
        others_allowed: When true, allow deleting other users' conversations.

    Returns:
        True when a row was removed.

    Raises:
        ConversationAccessDeniedError: Caller may not delete this conversation.
        DisplayHistoryDatabaseError: Database operation failed.

    """
    normalized = normalize_conversation_id(conversation_id)
    if not check_conversation_access(normalized, user_id, others_allowed):
        raise ConversationAccessDeniedError(normalized, user_id)
    deleted = delete_conversation_row(normalized)
    logger.info(
        "Deleted conversation %s for user %s: %s",
        normalized,
        user_id,
        deleted,
    )
    return deleted


def update_conversation_topic(
    conversation_id: str,
    user_id: str,
    others_allowed: bool,
    topic_summary: str,
) -> None:
    """Update the conversation topic summary.

    Args:
        conversation_id: Conversation id; client prefix is optional.
        user_id: Authenticated user.
        others_allowed: When true, allow updating other users' conversations.
        topic_summary: New topic summary text.

    Raises:
        ConversationAccessDeniedError: Caller may not update this conversation.
        ConversationNotFoundError: Conversation does not exist.
        DisplayHistoryDatabaseError: Database operation failed.

    """
    normalized = normalize_conversation_id(conversation_id)
    get_user_conversation(normalized, user_id, others_allowed)
    update_conversation_topic_summary(normalized, topic_summary)
    logger.info(
        "Updated topic summary for conversation %s for user %s",
        normalized,
        user_id,
    )

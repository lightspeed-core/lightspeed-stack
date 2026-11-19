"""Map stored conversation rows onto the v3 conversation envelope."""

from __future__ import annotations

from conversations.display_history.agentic.models.conversation import (
    Conversation,
    ConversationMetadata,
)
from conversations.display_history.persistence.mapping.agent_turn import (
    map_chat_history,
)
from conversations.display_history.persistence.models import (
    UserAgenticTurn,
    UserConversation,
    UserTurn,
)


def map_conversation_metadata(row: UserConversation) -> ConversationMetadata:
    """Map a conversation row to list/get metadata.

    Args:
        row: Stored conversation row.

    Returns:
        Metadata without chat history.

    """
    return ConversationMetadata.model_validate(
        {
            "conversation_id": row.id,
            "created_at": row.created_at,
            "last_turn_at": row.last_message_at,
            "turn_count": row.message_count,
            "last_used_model": row.last_used_model,
            "last_used_provider": row.last_used_provider,
            "topic_summary": row.topic_summary or None,
        }
    )


def map_conversation(
    row: UserConversation,
    turns: list[UserTurn],
    agentic_turns: list[UserAgenticTurn],
) -> Conversation:
    """Map stored rows to a full v3 conversation.

    Args:
        row: Stored conversation row.
        turns: Turn envelopes for the conversation.
        agentic_turns: Agentic rows for the same conversation.

    Returns:
        Conversation including chat history.

    """
    return Conversation.model_validate(
        {
            **map_conversation_metadata(row).model_dump(),
            "chat_history": map_chat_history(turns, agentic_turns),
        }
    )

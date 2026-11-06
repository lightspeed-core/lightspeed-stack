"""Load, create, update, and delete stored conversations."""

from datetime import datetime
from typing import Optional

from conversations.display_history.persistence.session import display_history_session
from models.database.conversations import UserConversation


def get_conversation_by_id(conversation_id: str) -> Optional[UserConversation]:
    """Load a conversation by id, or None if it does not exist."""
    with display_history_session("load conversation") as session:
        return session.query(UserConversation).filter_by(id=conversation_id).first()


def get_conversation_owner_user_id(conversation_id: str) -> Optional[str]:
    """Load the owner user id for a conversation, or None if it does not exist."""
    with display_history_session("resolve conversation owner") as session:
        return (
            session.query(UserConversation.user_id)
            .filter(UserConversation.id == conversation_id)
            .scalar()
        )


def list_conversations_for_user(user_id: str) -> list[UserConversation]:
    """List conversations owned by the given user."""
    with display_history_session("list conversations for user") as session:
        return session.query(UserConversation).filter_by(user_id=user_id).all()


def list_conversations() -> list[UserConversation]:
    """List all stored conversations."""
    with display_history_session("list conversations") as session:
        return session.query(UserConversation).all()


def insert_conversation(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    conversation_id: str,
    user_id: str,
    last_used_model: str,
    last_used_provider: str,
    topic_summary: str,
    message_count: int,
    last_response_id: Optional[str],
) -> UserConversation:
    """Create a conversation and return the saved record."""
    with display_history_session("create conversation") as session:
        conversation = UserConversation(
            id=conversation_id,
            user_id=user_id,
            last_used_model=last_used_model,
            last_used_provider=last_used_provider,
            topic_summary=topic_summary,
            message_count=message_count,
            last_response_id=last_response_id,
        )
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        return conversation


def update_conversation_metadata(
    conversation_id: str,
    *,
    last_used_model: str,
    last_used_provider: str,
    last_message_at: datetime,
    last_response_id: Optional[str],
) -> bool:
    """Refresh conversation metadata after a completed turn.

    Returns:
        True if updated, False if the conversation does not exist.

    """
    with display_history_session("update conversation metadata") as session:
        conversation = (
            session.query(UserConversation).filter_by(id=conversation_id).first()
        )
        if conversation is None:
            return False
        conversation.last_used_model = last_used_model
        conversation.last_used_provider = last_used_provider
        conversation.last_message_at = last_message_at
        conversation.message_count += 1
        if last_response_id is not None:
            conversation.last_response_id = last_response_id
        session.commit()
        return True


def update_conversation_topic_summary(conversation_id: str, topic_summary: str) -> bool:
    """Update the topic summary for a conversation.

    Returns:
        True if updated, False if the conversation does not exist.

    """
    with display_history_session("update conversation topic summary") as session:
        conversation = (
            session.query(UserConversation).filter_by(id=conversation_id).first()
        )
        if conversation is None:
            return False
        conversation.topic_summary = topic_summary
        session.commit()
        return True


def delete_conversation(conversation_id: str) -> bool:
    """Delete a conversation. Returns True if one was removed."""
    with display_history_session("delete conversation") as session:
        db_conversation = (
            session.query(UserConversation).filter_by(id=conversation_id).first()
        )
        if db_conversation is None:
            return False
        session.delete(db_conversation)
        session.commit()
        return True

"""Check who may read saved conversations."""

from conversations.display_history.errors import (
    ConversationAccessDeniedError,
    ConversationNotFoundError,
)
from conversations.display_history.persistence.models import UserConversation
from conversations.display_history.persistence.repository.conversation import (
    get_conversation_by_id,
    get_conversation_owner_user_id,
)


def check_conversation_access(
    conversation_id: str,
    user_id: str,
    others_allowed: bool,
) -> bool:
    """Return whether access is permitted under the policy.

    Args:
        conversation_id: Conversation to check.
        user_id: User requesting access.
        others_allowed: Whether other users' conversations are readable.

    Returns:
        True when access is permitted under the policy.

    """
    if others_allowed:
        return True
    owner_user_id = get_conversation_owner_user_id(conversation_id)
    if owner_user_id is None:
        return True
    return owner_user_id == user_id


def get_user_conversation(
    conversation_id: str,
    user_id: str,
    others_allowed: bool,
) -> UserConversation:
    """Load a conversation when the user is allowed to read it.

    Args:
        conversation_id: Conversation to load.
        user_id: User requesting access.
        others_allowed: Whether other users conversations are readable.

    Returns:
        The conversation row.

    Raises:
        ConversationAccessDeniedError: User may not read this conversation.
        ConversationNotFoundError: Conversation does not exist.
        DisplayHistoryDatabaseError: Database operation failed.

    """
    if not check_conversation_access(conversation_id, user_id, others_allowed):
        raise ConversationAccessDeniedError(conversation_id, user_id)
    conversation = get_conversation_by_id(conversation_id)
    if conversation is None:
        raise ConversationNotFoundError(conversation_id)
    return conversation

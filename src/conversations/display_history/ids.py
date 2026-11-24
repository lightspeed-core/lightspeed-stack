"""Validate client conversation identifiers for display-history APIs."""

from conversations.display_history.errors import InvalidConversationIdError
from log import get_logger
from utils.suid import check_suid

logger = get_logger(__name__)


def validate_conversation_id(conversation_id: str) -> None:
    """Reject conversation ids that are not valid SUIDs.

    Args:
        conversation_id: Value from a path or query parameter.

    Raises:
        InvalidConversationIdError: The id format is not accepted.

    """
    if not check_suid(conversation_id):
        logger.error("Invalid conversation ID format: %s", conversation_id)
        raise InvalidConversationIdError(conversation_id)

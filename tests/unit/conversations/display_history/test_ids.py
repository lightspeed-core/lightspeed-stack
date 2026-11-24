"""Tests for display-history conversation id validation."""

import pytest
from pytest_mock import MockerFixture

from conversations.display_history.errors import InvalidConversationIdError
from conversations.display_history.ids import validate_conversation_id

VALID_CONVERSATION_ID = "123e4567-e89b-12d3-a456-426614174000"
INVALID_CONVERSATION_ID = "invalid-id"


def test_validate_conversation_id_accepts_uuid() -> None:
    """UUID conversation ids are accepted."""
    validate_conversation_id(VALID_CONVERSATION_ID)


def test_validate_conversation_id_rejects_invalid(mocker: MockerFixture) -> None:
    """Invalid ids raise InvalidConversationIdError."""
    mocker.patch(
        "conversations.display_history.ids.check_suid",
        return_value=False,
    )
    with pytest.raises(InvalidConversationIdError) as exc_info:
        validate_conversation_id(INVALID_CONVERSATION_ID)
    assert exc_info.value.conversation_id == INVALID_CONVERSATION_ID

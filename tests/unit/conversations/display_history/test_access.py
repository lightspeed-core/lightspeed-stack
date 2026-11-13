"""Tests for display_history.access."""

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from conversations.display_history.access import (
    check_conversation_access,
    get_user_conversation,
)
from conversations.display_history.errors import (
    ConversationAccessDeniedError,
    ConversationNotFoundError,
)
from tests.unit.conversations.display_history.persistence.sample_rows import (
    SAMPLE_CONVERSATION,
    seed_sample_conversation_and_turn,
)


@pytest.mark.usefixtures("patch_display_history_session")
def test_check_conversation_access_owner(memory_engine: Engine) -> None:
    """Owners pass when others are not allowed."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
    assert check_conversation_access(
        SAMPLE_CONVERSATION["id"],
        SAMPLE_CONVERSATION["user_id"],
        False,
    )


@pytest.mark.usefixtures("patch_display_history_session")
def test_check_conversation_access_other_user_denied(memory_engine: Engine) -> None:
    """Non-owners fail when others are not allowed."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
    assert not check_conversation_access(
        SAMPLE_CONVERSATION["id"],
        "other-user",
        False,
    )


@pytest.mark.usefixtures("patch_display_history_session")
def test_check_conversation_access_other_user_allowed(memory_engine: Engine) -> None:
    """Non-owners pass when others' conversations are readable."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
    assert check_conversation_access(
        SAMPLE_CONVERSATION["id"],
        "other-user",
        True,
    )


@pytest.mark.usefixtures("patch_display_history_session")
def test_check_conversation_access_missing_conversation() -> None:
    """Missing conversations are not treated as forbidden by policy alone."""
    assert check_conversation_access("missing-conv", "user-1", False)


@pytest.mark.usefixtures("patch_display_history_session")
def test_get_user_conversation_success(memory_engine: Engine) -> None:
    """Access check and load return the conversation row."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
    row = get_user_conversation(
        SAMPLE_CONVERSATION["id"],
        SAMPLE_CONVERSATION["user_id"],
        False,
    )
    assert row.id == SAMPLE_CONVERSATION["id"]


@pytest.mark.usefixtures("patch_display_history_session")
def test_get_user_conversation_forbidden(memory_engine: Engine) -> None:
    """Forbidden readers raise ConversationAccessDeniedError."""
    with Session(memory_engine) as session:
        seed_sample_conversation_and_turn(session)
    with pytest.raises(ConversationAccessDeniedError):
        get_user_conversation(
            SAMPLE_CONVERSATION["id"],
            "other-user",
            False,
        )


@pytest.mark.usefixtures("patch_display_history_session")
def test_get_user_conversation_not_found() -> None:
    """Missing conversations raise ConversationNotFoundError."""
    with pytest.raises(ConversationNotFoundError):
        get_user_conversation("missing-conv", "user-1", True)

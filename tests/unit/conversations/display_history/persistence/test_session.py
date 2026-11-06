"""Tests for display_history_session."""

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from conversations.display_history.errors import DisplayHistoryDatabaseError
from conversations.display_history.persistence.session import display_history_session
from models.database.conversations import UserConversation


def test_sqlalchemy_error_becomes_display_history_database_error(
    mocker: MockerFixture,
) -> None:
    """Database errors become DisplayHistoryDatabaseError."""
    mock_session = mocker.MagicMock(spec=Session)
    mock_session.__enter__ = mocker.Mock(return_value=mock_session)
    mock_session.__exit__ = mocker.Mock(return_value=False)
    mock_session.query.side_effect = SQLAlchemyError("connection lost")

    mocker.patch(
        "conversations.display_history.persistence.session.get_session",
        return_value=mock_session,
    )

    with pytest.raises(
        DisplayHistoryDatabaseError,
        match="Display history load conversation failed",
    ):
        with display_history_session("load conversation") as session:
            session.query(UserConversation)

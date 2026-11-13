"""Database sessions for display history persistence."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_session
from conversations.display_history.errors import DisplayHistoryDatabaseError


@contextmanager
def display_history_session(operation: str) -> Iterator[Session]:
    """Provide a database session for one persistence action.

    Args:
        operation: Short label included in errors when the database fails.

    Raises:
        DisplayHistoryDatabaseError: If the database returns an error.

    """
    try:
        with get_session() as session:
            yield session
    except SQLAlchemyError as exc:
        raise DisplayHistoryDatabaseError(operation) from exc

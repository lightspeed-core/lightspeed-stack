"""Register domain exception handlers on the FastAPI application."""

from fastapi import FastAPI

from app.exceptions.mappings import conversation_exception_handler
from conversations.display_history.errors import ConversationHistoryError


def register_application_exception_handlers(app: FastAPI) -> None:
    """Wire domain exception handlers onto the FastAPI application.

    Args:
        app: Application instance to configure.

    """
    app.add_exception_handler(
        ConversationHistoryError,
        conversation_exception_handler,
    )

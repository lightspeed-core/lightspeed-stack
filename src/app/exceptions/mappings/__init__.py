"""HTTP mappings for application exceptions, one module per API domain."""

from app.exceptions.mappings.conversations import conversation_exception_handler

__all__ = [
    "conversation_exception_handler",
]

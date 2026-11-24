"""Map conversation history domain errors to OpenAPI HTTP error bodies."""

from collections.abc import Callable
from typing import Final

from fastapi import Request

from app.exceptions.base import module_exception_handler
from conversations.display_history.errors import (
    ConversationAccessDeniedError,
    ConversationHistoryDatabaseError,
    ConversationHistoryError,
    ConversationNotFoundError,
    InvalidConversationIdError,
    TurnNotFoundError,
)
from models.api.responses.error import (
    BadRequestResponse,
    ForbiddenResponse,
    InternalServerErrorResponse,
    NotFoundResponse,
)
from models.api.responses.error.bases import AbstractErrorResponse


def _conversation_action_from_method(request: Request) -> str:
    """Return the conversation action implied by the HTTP method."""
    match request.method:
        case "GET":
            return "read"
        case "DELETE":
            return "delete"
        case "PUT" | "PATCH":
            return "update"
        case _:
            return "access"


def _conversation_not_found(
    _request: Request, exc: ConversationNotFoundError
) -> NotFoundResponse:
    """Build HTTP 404 when a conversation id does not exist."""
    return NotFoundResponse(resource="conversation", resource_id=exc.conversation_id)


def _turn_not_found(_request: Request, exc: TurnNotFoundError) -> NotFoundResponse:
    """Build HTTP 404 when a prior response id has no saved turn."""
    return NotFoundResponse(resource="response", resource_id=exc.response_id)


def _conversation_access_denied(
    request: Request, exc: ConversationAccessDeniedError
) -> ForbiddenResponse:
    """Build HTTP 403 when the user may not access the conversation."""
    action = _conversation_action_from_method(request)
    return ForbiddenResponse.conversation(
        action=action,
        resource_id=exc.conversation_id,
        user_id=exc.user_id,
    )


def _conversation_history_database_error(
    _request: Request, exc: ConversationHistoryDatabaseError
) -> InternalServerErrorResponse:
    """Build HTTP 500 when conversation history persistence fails."""
    return InternalServerErrorResponse.database_error_for_operation(exc.operation)


def _invalid_conversation_id(
    _request: Request, exc: InvalidConversationIdError
) -> BadRequestResponse:
    """Build HTTP 400 when a conversation id is not a valid SUID."""
    return BadRequestResponse(resource="conversation", resource_id=exc.conversation_id)


CONVERSATION_HTTP_MAPPINGS: Final[
    dict[type[ConversationHistoryError], Callable[..., AbstractErrorResponse]]
] = {
    ConversationNotFoundError: _conversation_not_found,
    TurnNotFoundError: _turn_not_found,
    ConversationAccessDeniedError: _conversation_access_denied,
    ConversationHistoryDatabaseError: _conversation_history_database_error,
    InvalidConversationIdError: _invalid_conversation_id,
}

conversation_exception_handler = module_exception_handler(CONVERSATION_HTTP_MAPPINGS)

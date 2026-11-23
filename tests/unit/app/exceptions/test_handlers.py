"""Tests for application exception handler registration and serialization."""

import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.exceptions.handlers import register_application_exception_handlers
from app.exceptions.mappings import conversation_exception_handler
from conversations.display_history.errors import (
    ConversationHistoryError,
    ConversationNotFoundError,
)
from models.api.responses.error import (
    InternalServerErrorResponse,
    NotFoundResponse,
)
from models.api.responses.error.bases import AbstractErrorResponse
from tests.unit.app.exceptions.helpers import (
    CONVERSATION_ID,
    UnmappedConversationHistoryError,
    http_request,
)


def _assert_matches_http_exception(
    response: JSONResponse, error: AbstractErrorResponse
) -> None:
    """JSON body matches FastAPI HTTPException(**error.model_dump())."""
    http_exc = HTTPException(**error.model_dump())
    assert response.status_code == http_exc.status_code
    assert json.loads(bytes(response.body)) == {"detail": http_exc.detail}


def test_register_application_exception_handlers() -> None:
    """Conversation history errors are handled through the domain base class."""
    app = FastAPI()
    register_application_exception_handlers(app)
    assert (
        app.exception_handlers[ConversationHistoryError]
        is conversation_exception_handler
    )


def test_handler_serializes_mapped_error_like_http_exception() -> None:
    """Mapped errors become JSON with the same detail envelope as HTTPException."""
    response = conversation_exception_handler(
        http_request(),
        ConversationNotFoundError(CONVERSATION_ID),
    )
    _assert_matches_http_exception(
        response,
        NotFoundResponse(resource="conversation", resource_id=CONVERSATION_ID),
    )


def test_unmapped_error_is_sanitized() -> None:
    """Unmapped domain errors return a generic 500 without internal details."""
    response = conversation_exception_handler(
        http_request(),
        UnmappedConversationHistoryError(),
    )
    assert b"secret-internal-detail" not in response.body
    _assert_matches_http_exception(response, InternalServerErrorResponse.generic())

"""Tests for conversation HTTP exception mappings."""

import pytest

from app.exceptions.mappings.conversations import CONVERSATION_HTTP_MAPPINGS
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
from tests.unit.app.exceptions.helpers import (
    CONVERSATION_ID,
    RESPONSE_ID,
    USER_ID,
    UnmappedConversationHistoryError,
    http_request,
)


class _DerivedNotFound(ConversationNotFoundError):
    """Test-only subclass of a mapped exception."""


@pytest.mark.parametrize(
    ("exc", "expected", "method"),
    [
        (
            ConversationNotFoundError(CONVERSATION_ID),
            NotFoundResponse(resource="conversation", resource_id=CONVERSATION_ID),
            "GET",
        ),
        (
            TurnNotFoundError(RESPONSE_ID),
            NotFoundResponse(resource="response", resource_id=RESPONSE_ID),
            "GET",
        ),
        (
            InvalidConversationIdError("invalid-id"),
            BadRequestResponse(resource="conversation", resource_id="invalid-id"),
            "GET",
        ),
        (
            ConversationHistoryDatabaseError("list conversations"),
            InternalServerErrorResponse.database_error_for_operation(
                "list conversations"
            ),
            "GET",
        ),
    ],
    ids=[
        "conversation_not_found",
        "turn_not_found",
        "invalid_conversation_id",
        "database_error",
    ],
)
def test_mapping_matches_api_contract(
    exc: ConversationHistoryError,
    expected: AbstractErrorResponse,
    method: str,
) -> None:
    """Each mapped exception rebuilds the matching OpenAPI error model."""
    actual = CONVERSATION_HTTP_MAPPINGS[type(exc)](http_request(method), exc)
    assert actual.model_dump() == expected.model_dump()


@pytest.mark.parametrize(
    ("method", "action"),
    [
        ("GET", "read"),
        ("DELETE", "delete"),
        ("PUT", "update"),
        ("PATCH", "update"),
        ("POST", "access"),
    ],
)
def test_access_denied_uses_http_method_as_action(method: str, action: str) -> None:
    """Forbidden bodies take the action from the request method."""
    exc = ConversationAccessDeniedError(CONVERSATION_ID, USER_ID)
    expected = ForbiddenResponse.conversation(
        action=action,
        resource_id=CONVERSATION_ID,
        user_id=USER_ID,
    )
    actual = CONVERSATION_HTTP_MAPPINGS[type(exc)](http_request(method), exc)
    assert actual.model_dump() == expected.model_dump()


@pytest.mark.parametrize(
    "exc_type",
    [
        ConversationHistoryError,
        UnmappedConversationHistoryError,
        _DerivedNotFound,
    ],
    ids=["base", "unmapped_subclass", "mapped_parent_subclass"],
)
def test_exact_type_lookup_skips_unmapped_types(
    exc_type: type[ConversationHistoryError],
) -> None:
    """Only concrete mapped types are dict keys; subclasses do not inherit entries."""
    assert exc_type not in CONVERSATION_HTTP_MAPPINGS

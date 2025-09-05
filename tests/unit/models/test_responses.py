"""Tests for QueryResponse. StatusResponse, AuthorizedResponse, and UnauthorizedResponse models."""

import pytest

from pydantic import ValidationError

from models.responses import (
    QueryResponse,
    StatusResponse,
    AuthorizedResponse,
    UnauthorizedResponse,
)


class TestQueryResponse:
    """Test cases for the QueryResponse model."""

    def test_constructor(self) -> None:
        """Test the QueryResponse constructor."""
        qr = QueryResponse(
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
            response="LLM answer",
        )
        assert qr.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert qr.response == "LLM answer"

    def test_optional_conversation_id(self) -> None:
        """Test the QueryResponse with default conversation ID."""
        qr = QueryResponse(response="LLM answer")
        assert qr.conversation_id is None
        assert qr.response == "LLM answer"


class TestStatusResponse:
    """Test cases for the StatusResponse model."""

    def test_constructor_feedback_enabled(self) -> None:
        """Test the StatusResponse constructor."""
        sr = StatusResponse(functionality="feedback", status={"enabled": True})
        assert sr.functionality == "feedback"
        assert sr.status == {"enabled": True}

    def test_constructor_feedback_disabled(self) -> None:
        """Test the StatusResponse constructor."""
        sr = StatusResponse(functionality="feedback", status={"enabled": False})
        assert sr.functionality == "feedback"
        assert sr.status == {"enabled": False}


class TestAuthorizedResponse:
    """Test cases for the AuthorizedResponse model."""

    def test_constructor(self) -> None:
        """Test the AuthorizedResponse constructor."""
        ar = AuthorizedResponse(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            username="testuser",
            skip_userid_check=True,
        )
        assert ar.user_id == "123e4567-e89b-12d3-a456-426614174000"
        assert ar.username == "testuser"
        assert ar.skip_userid_check is True

    def test_constructor_fields_required(self) -> None:
        """Test the AuthorizedResponse constructor."""
        with pytest.raises(ValidationError):
            AuthorizedResponse(username="testuser")  # pyright: ignore

        with pytest.raises(ValidationError):
            AuthorizedResponse(
                user_id="123e4567-e89b-12d3-a456-426614174000"
            )  # pyright: ignore


class TestUnauthorizedResponse:
    """Test cases for the UnauthorizedResponse model."""

    def test_constructor(self) -> None:
        """Test the UnauthorizedResponse constructor."""
        ur = UnauthorizedResponse(
            detail="Missing or invalid credentials provided by client"
        )
        assert ur.detail == "Missing or invalid credentials provided by client"

    def test_constructor_fields_required(self) -> None:
        """Test the UnauthorizedResponse constructor."""
        with pytest.raises(Exception):
            UnauthorizedResponse()  # pyright: ignore

"""Unit tests for AuthorizedResponse model."""

import pytest
from pydantic import ValidationError

from models.responses import AuthorizedResponse


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
        """Test the AuthorizedResponse constructor.

        Verify that constructing AuthorizedResponse without required fields
        raises ValidationError.

        Checks three cases where a ValidationError is expected:
        - no parameters provided
        - missing `user_id`
        - missing `username`
        """
        with pytest.raises(ValidationError):
            # missing all parameters
            _ = AuthorizedResponse()  # pyright: ignore

        with pytest.raises(ValidationError):
            # missing user_id parameter
            _ = AuthorizedResponse(username="testuser")  # pyright: ignore

        with pytest.raises(ValidationError):
            # missing username parameter
            _ = AuthorizedResponse(
                user_id="123e4567-e89b-12d3-a456-426614174000"
            )  # pyright: ignore

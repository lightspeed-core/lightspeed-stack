"""Test configuration validation for unknown fields."""

import pytest
from pydantic import ValidationError

from models.config import ServiceConfiguration


def test_configuration_rejects_unknown_fields() -> None:
    """Test that configuration models reject unknown fields."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ServiceConfiguration(
            host="localhost", port=8080, unknown_field="should_fail"
        )  # pyright: ignore[reportCallIssue]

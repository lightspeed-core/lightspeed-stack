"""Unit tests for GraniteGuardianConfig model."""

import pytest
from pydantic import ValidationError

from models.config import GraniteGuardianConfig, RiskDefinition


def _make_risk() -> RiskDefinition:
    """Build a minimal RiskDefinition for testing."""
    return RiskDefinition(
        name="test_risk",
        description="test description",
        points=["input"],
        violation_message="Blocked.",
    )


def test_https_url_with_api_key_is_valid() -> None:
    """Test that an https URL with an api_key is accepted."""
    config = GraniteGuardianConfig(
        url="https://example.com/v1",
        api_key="test-key",
        risks=[_make_risk()],
    )
    assert config.api_key is not None


def test_http_url_without_api_key_is_valid() -> None:
    """Test that an http URL is accepted when no api_key is configured."""
    config = GraniteGuardianConfig(
        url="http://example.com/v1",
        risks=[_make_risk()],
    )
    assert config.api_key is None


def test_http_url_with_api_key_is_rejected() -> None:
    """Test that a ValidationError is raised when api_key is set but URL is not HTTPS."""
    with pytest.raises(
        ValidationError,
        match="Granite Guardian endpoints with an API key must use HTTPS",
    ):
        GraniteGuardianConfig(
            url="http://example.com/v1",
            api_key="test-key",
            risks=[_make_risk()],
        )

"""Unit tests for the /health REST API endpoint."""

from models.common import (
    ProviderHealthStatus,
)


class TestProviderHealthStatus:
    """Test cases for the ProviderHealthStatus model."""

    def test_provider_health_status_creation(self) -> None:
        """Test creating a ProviderHealthStatus instance."""
        status = ProviderHealthStatus(
            provider_id="test_provider", status="ok", message="All good"
        )
        assert status.provider_id == "test_provider"
        assert status.status == "ok"
        assert status.message == "All good"

    def test_provider_health_status_optional_fields(self) -> None:
        """Test creating a ProviderHealthStatus with minimal fields."""
        status = ProviderHealthStatus(
            provider_id="test_provider", status="ok", message=None
        )
        assert status.provider_id == "test_provider"
        assert status.status == "ok"
        assert status.message is None

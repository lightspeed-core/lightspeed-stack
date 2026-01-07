"""Unit tests for QuotaSchedulerConfig model."""

import pytest

from pydantic import ValidationError

from models.config import QuotaSchedulerConfiguration


def test_quota_scheduler_default_configuration() -> None:
    """Test the default configuration."""
    cfg = QuotaSchedulerConfiguration()
    assert cfg is not None
    # default value
    assert cfg.period == 1
    assert cfg.database_reconnection_count == 10
    assert cfg.database_reconnection_delay == 1


def test_quota_scheduler_custom_configuration() -> None:
    """Test the custom configuration.

    Verify that QuotaSchedulerConfiguration accepts a custom period value.

    Constructs a QuotaSchedulerConfiguration with period=10 and asserts the
    instance is created and its period equals 10 (the input value).
    """
    cfg = QuotaSchedulerConfiguration(
        period=10,
        database_reconnection_count=2,
        database_reconnection_delay=3,
    )
    assert cfg is not None
    assert cfg.period == 10
    assert cfg.database_reconnection_count == 2
    assert cfg.database_reconnection_delay == 3


def test_quota_scheduler_custom_configuration_zero_period() -> None:
    """Test that zero period value raises ValidationError."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        QuotaSchedulerConfiguration(period=0)


def test_quota_scheduler_custom_configuration_negative_period() -> None:
    """Test that negative period value raises ValidationError."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        QuotaSchedulerConfiguration(period=-10)


def test_quota_scheduler_custom_configuration_zero_reconnection_count() -> None:
    """Test that zero database reconnection count value raises ValidationError."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        QuotaSchedulerConfiguration(database_reconnection_count=0)


def test_quota_scheduler_custom_configuration_negative_reconnection_count() -> None:
    """Test that negative database reconnection count value raises ValidationError."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        QuotaSchedulerConfiguration(database_reconnection_count=-10)


def test_quota_scheduler_custom_configuration_zero_reconnection_delay() -> None:
    """Test that zero database reconnection delay value raises ValidationError."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        QuotaSchedulerConfiguration(database_reconnection_delay=0)


def test_quota_scheduler_custom_configuration_negative_reconnection_delay() -> None:
    """Test that negative database reconnection delay value raises ValidationError."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        QuotaSchedulerConfiguration(database_reconnection_delay=-10)

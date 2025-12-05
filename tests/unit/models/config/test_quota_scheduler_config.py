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


def test_quota_scheduler_custom_configuration() -> None:
    """Test the custom configuration."""
    cfg = QuotaSchedulerConfiguration(period=10)
    assert cfg is not None
    assert cfg.period == 10


def test_quota_scheduler_custom_configuration_zero_period() -> None:
    """Test that zero period value raises ValidationError."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        QuotaSchedulerConfiguration(period=0)


def test_quota_scheduler_custom_configuration_negative_period() -> None:
    """Test that negative period value raises ValidationError."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        QuotaSchedulerConfiguration(period=-10)

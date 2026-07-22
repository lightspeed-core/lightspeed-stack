"""Unit tests for QuotaSchedulerConfig model."""

from typing import Any

import pytest
from pydantic import ValidationError

from lightspeed_stack.models.config import QuotaSchedulerConfiguration


def test_quota_scheduler_default_configuration() -> None:
    """Test the default configuration."""
    cfg = QuotaSchedulerConfiguration()  # pyright: ignore[reportCallIssue]
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
        QuotaSchedulerConfiguration(period=0)  # pyright: ignore[reportCallIssue]


def test_quota_scheduler_custom_configuration_negative_period() -> None:
    """Test that negative period value raises ValidationError."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        QuotaSchedulerConfiguration(period=-10)  # pyright: ignore[reportCallIssue]


def test_quota_scheduler_custom_configuration_zero_reconnection_count() -> None:
    """Test that zero database reconnection count value raises ValidationError."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        QuotaSchedulerConfiguration(
            database_reconnection_count=0
        )  # pyright: ignore[reportCallIssue]


def test_quota_scheduler_custom_configuration_negative_reconnection_count() -> None:
    """Test that negative database reconnection count value raises ValidationError."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        QuotaSchedulerConfiguration(
            database_reconnection_count=-10
        )  # pyright: ignore[reportCallIssue]


def test_quota_scheduler_custom_configuration_zero_reconnection_delay() -> None:
    """Test that zero database reconnection delay value raises ValidationError."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        QuotaSchedulerConfiguration(
            database_reconnection_delay=0
        )  # pyright: ignore[reportCallIssue]


def test_quota_scheduler_custom_configuration_negative_reconnection_delay() -> None:
    """Test that negative database reconnection delay value raises ValidationError."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        QuotaSchedulerConfiguration(
            database_reconnection_delay=-10
        )  # pyright: ignore[reportCallIssue]


correct_configurations = [
    {
        "period": 959,
        "database_reconnection_count": 125,
        "database_reconnection_delay": 94,
    },
    {
        "period": 1,
        "database_reconnection_count": 125,
        "database_reconnection_delay": 94,
    },
    {
        "period": 959,
        "database_reconnection_count": 1,
        "database_reconnection_delay": 94,
    },
    {
        "period": 959,
        "database_reconnection_count": 125,
        "database_reconnection_delay": 1,
    },
]


@pytest.mark.parametrize("config_dict", correct_configurations)
def test_configure_quota_scheduler_from_dict(
    config_dict: dict[str, Any],
) -> None:
    """Test the configuration initialization from dictionary with config values."""
    QuotaSchedulerConfiguration(**config_dict)


incorrect_configurations = [
    {
        "period": -1,
        "database_reconnection_count": 125,
        "database_reconnection_delay": 94,
    },
    {
        "period": 1,
        "database_reconnection_count": -1,
        "database_reconnection_delay": 94,
    },
    {
        "period": 959,
        "database_reconnection_count": 1,
        "database_reconnection_delay": -1,
    },
    {
        "period": None,
        "database_reconnection_count": 125,
        "database_reconnection_delay": 94,
    },
    {
        "period": 1,
        "database_reconnection_count": None,
        "database_reconnection_delay": 94,
    },
    {
        "period": 959,
        "database_reconnection_count": 1,
        "database_reconnection_delay": None,
    },
    {
        "period": "not a number",
        "database_reconnection_count": 125,
        "database_reconnection_delay": 94,
    },
    {
        "period": 1,
        "database_reconnection_count": "not a number",
        "database_reconnection_delay": 94,
    },
    {
        "period": 959,
        "database_reconnection_count": 1,
        "database_reconnection_delay": "not a number",
    },
]


@pytest.mark.parametrize("config_dict", incorrect_configurations)
def test_configure_quota_scheduler_from_dict_negative_cases(
    config_dict: dict[str, Any],
) -> None:
    """Test the configuration initialization from dictionary with config values."""
    with pytest.raises(ValueError, match="validation error"):
        # try to initialize the app config and load configuration from a Python
        # dictionary
        QuotaSchedulerConfiguration(**config_dict)

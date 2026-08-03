"""Unit tests for QuotaLimiterConfig model."""

from typing import Any

import pytest
from pytest_subtests import SubTests

from lightspeed_stack.models.config import QuotaLimiterConfiguration


def test_quota_limiter_configuration(subtests: SubTests) -> None:
    """Test the default configuration."""
    with subtests.test(msg="Zero initial quota"):
        cfg = QuotaLimiterConfiguration(
            type="cluster_limiter",
            name="cluster_monthly_limits",
            initial_quota=0,
            quota_increase=10,
            period="3 seconds",
        )
        assert cfg is not None
        assert cfg.type == "cluster_limiter"
        assert cfg.name == "cluster_monthly_limits"
        assert cfg.initial_quota == 0
        assert cfg.quota_increase == 10
        assert cfg.period == "3 seconds"

    with subtests.test(msg="Non zero initial quota"):
        cfg = QuotaLimiterConfiguration(
            type="cluster_limiter",
            name="cluster_monthly_limits",
            initial_quota=42,
            quota_increase=10,
            period="3 seconds",
        )
        assert cfg is not None
        assert cfg.type == "cluster_limiter"
        assert cfg.name == "cluster_monthly_limits"
        assert cfg.initial_quota == 42
        assert cfg.quota_increase == 10
        assert cfg.period == "3 seconds"

    with subtests.test(msg="Zero quota increase"):
        cfg = QuotaLimiterConfiguration(
            type="cluster_limiter",
            name="cluster_monthly_limits",
            initial_quota=10,
            quota_increase=0,
            period="3 seconds",
        )
        assert cfg is not None
        assert cfg.type == "cluster_limiter"
        assert cfg.name == "cluster_monthly_limits"
        assert cfg.initial_quota == 10
        assert cfg.quota_increase == 0
        assert cfg.period == "3 seconds"

    with subtests.test(msg="Non zero quota increase"):
        cfg = QuotaLimiterConfiguration(
            type="cluster_limiter",
            name="cluster_monthly_limits",
            initial_quota=10,
            quota_increase=42,
            period="3 seconds",
        )
        assert cfg is not None
        assert cfg.type == "cluster_limiter"
        assert cfg.name == "cluster_monthly_limits"
        assert cfg.initial_quota == 10
        assert cfg.quota_increase == 42
        assert cfg.period == "3 seconds"

    with subtests.test(msg="User limiter"):
        cfg = QuotaLimiterConfiguration(
            type="user_limiter",
            name="user_monthly_limits",
            initial_quota=10,
            quota_increase=42,
            period="3 seconds",
        )
        assert cfg is not None
        assert cfg.type == "user_limiter"
        assert cfg.name == "user_monthly_limits"
        assert cfg.initial_quota == 10
        assert cfg.quota_increase == 42
        assert cfg.period == "3 seconds"


def test_quota_limiter_configuration_improper_values(subtests: SubTests) -> None:
    """Test the quota limiter configuration initialization with improper values."""
    with subtests.test(msg="Negative initial quota value"):
        # Verify that providing a negative `initial_quota` raises a ValueError.
        #
        # Verify that constructing a QuotaLimiterConfiguration with a negative
        # `initial_quota` raises a ValueError with message "Input should be
        # greater than or equal to 0".
        with pytest.raises(
            ValueError, match="Input should be greater than or equal to 0"
        ):
            _ = QuotaLimiterConfiguration(
                type="cluster_limiter",
                name="cluster_monthly_limits",
                initial_quota=-1,
                quota_increase=10,
                period="3 seconds",
            )

    with subtests.test(msg="Negative quota increase value"):
        # Verify that providing a negative `quota_increase` raises a ValueError.

        # Asserts that constructing a QuotaLimiterConfiguration with `quota_increase`
        # less than zero raises a ValueError with the message "Input should be
        # greater than or equal to 0".
        with pytest.raises(
            ValueError, match="Input should be greater than or equal to 0"
        ):
            _ = QuotaLimiterConfiguration(
                type="cluster_limiter",
                name="cluster_monthly_limits",
                initial_quota=1,
                quota_increase=-10,
                period="3 seconds",
            )

    with subtests.test(msg="Negative initial quota and quota increase value"):
        # Verify that providing a negative `quota_increase` raises a ValueError.

        # Asserts that constructing a QuotaLimiterConfiguration with `quota_increase`
        # less than zero raises a ValueError with the message "Input should be
        # greater than or equal to 0".
        with pytest.raises(
            ValueError, match="Input should be greater than or equal to 0"
        ):
            _ = QuotaLimiterConfiguration(
                type="cluster_limiter",
                name="cluster_monthly_limits",
                initial_quota=-1,
                quota_increase=-10,
                period="3 seconds",
            )

    with subtests.test(msg="Improper quota limiter"):
        # Check that constructing QuotaLimiterConfiguration with an invalid `type`
        # raises a ValueError with the expected message.
        with pytest.raises(
            ValueError, match="Input should be 'user_limiter' or 'cluster_limiter'"
        ):
            _ = QuotaLimiterConfiguration(
                type="unknown_limiter",  # pyright: ignore[reportArgumentType]
                name="cluster_monthly_limits",
                initial_quota=1,
                quota_increase=10,
                period="3 seconds",
            )

    with subtests.test(msg="Improper period"):
        with pytest.raises(ValueError, match="Input should be a valid string"):
            _ = QuotaLimiterConfiguration(
                type="cluster_limiter",
                name="cluster_monthly_limits",
                initial_quota=1,
                quota_increase=10,
                period=3,
            )


correct_configurations = [
    {
        "type": "cluster_limiter",
        "name": "John Williams",
        "initial_quota": 212,
        "quota_increase": 583,
        "period": "Series trouble fund skill.",
    },
    {
        "type": "cluster_limiter",
        "name": "Frank Levine",
        "initial_quota": 616,
        "quota_increase": 40,
        "period": "Eye idea western skill able although happy. Positi",
    },
    {
        "type": "cluster_limiter",
        "name": "Susan Walters",
        "initial_quota": 9,
        "quota_increase": 855,
        "period": "One stock pressure. Save worker benefit blue speak",
    },
    {
        "type": "cluster_limiter",
        "name": "Pamela Farmer",
        "initial_quota": 223,
        "quota_increase": 62,
        "period": "Expect chance or stop hard southern particularly.",
    },
    {
        "type": "cluster_limiter",
        "name": "Bobby Chandler",
        "initial_quota": 496,
        "quota_increase": 217,
        "period": "Where animal outside.",
    },
    {
        "type": "cluster_limiter",
        "name": "Jeffrey Butler",
        "initial_quota": 445,
        "quota_increase": 78,
        "period": "Song child mind. Sit win miss gas as.",
    },
    {
        "type": "cluster_limiter",
        "name": "Lydia Sweeney",
        "initial_quota": 375,
        "quota_increase": 953,
        "period": "Feel husband phone together summer.",
    },
    {
        "type": "cluster_limiter",
        "name": "Jacqueline Allen",
        "initial_quota": 147,
        "quota_increase": 277,
        "period": "Whose environmental life food bit young.",
    },
    {
        "type": "cluster_limiter",
        "name": "Matthew Williams",
        "initial_quota": 696,
        "quota_increase": 25,
        "period": "Perhaps girl organization ok continue.",
    },
    {
        "type": "cluster_limiter",
        "name": "Shawn Stone",
        "initial_quota": 126,
        "quota_increase": 547,
        "period": "Develop teach data.",
    },
    {
        "type": "user_limiter",
        "name": "John Williams",
        "initial_quota": 212,
        "quota_increase": 583,
        "period": "Series trouble fund skill.",
    },
    {
        "type": "user_limiter",
        "name": "Frank Levine",
        "initial_quota": 616,
        "quota_increase": 40,
        "period": "Eye idea western skill able although happy. Positi",
    },
    {
        "type": "user_limiter",
        "name": "Susan Walters",
        "initial_quota": 9,
        "quota_increase": 855,
        "period": "One stock pressure. Save worker benefit blue speak",
    },
    {
        "type": "user_limiter",
        "name": "Pamela Farmer",
        "initial_quota": 223,
        "quota_increase": 62,
        "period": "Expect chance or stop hard southern particularly.",
    },
    {
        "type": "user_limiter",
        "name": "Bobby Chandler",
        "initial_quota": 496,
        "quota_increase": 217,
        "period": "Where animal outside.",
    },
    {
        "type": "user_limiter",
        "name": "Jeffrey Butler",
        "initial_quota": 445,
        "quota_increase": 78,
        "period": "Song child mind. Sit win miss gas as.",
    },
    {
        "type": "user_limiter",
        "name": "Lydia Sweeney",
        "initial_quota": 375,
        "quota_increase": 953,
        "period": "Feel husband phone together summer.",
    },
    {
        "type": "user_limiter",
        "name": "Jacqueline Allen",
        "initial_quota": 147,
        "quota_increase": 277,
        "period": "Whose environmental life food bit young.",
    },
    {
        "type": "user_limiter",
        "name": "Matthew Williams",
        "initial_quota": 696,
        "quota_increase": 25,
        "period": "Perhaps girl organization ok continue.",
    },
    {
        "type": "user_limiter",
        "name": "Shawn Stone",
        "initial_quota": 126,
        "quota_increase": 547,
        "period": "Develop teach data.",
    },
]


@pytest.mark.parametrize("config_dict", correct_configurations)
def test_configure_quota_handlers_from_dict(config_dict: dict[str, Any]) -> None:
    """Test the configuration initialization from dictionary with config values."""
    # try to initialize the app config and load configuration from a Python
    # dictionary
    QuotaLimiterConfiguration(**config_dict)


incorrect_configurations = [
    {
        "type": "cluster_limiter",
        "name": "John Williams",
        "initial_quota": "foo",
        "quota_increase": 583,
        "period": "Series trouble fund skill.",
    },
    {
        "type": "cluster_limiter",
        "name": "Frank Levine",
        "initial_quota": 616,
        "quota_increase": "bar",
        "period": "Eye idea western skill able although happy. Positi",
    },
    {
        "type": "cluster_limiter",
        "name": "Susan Walters",
        "initial_quota": "foo",
        "quota_increase": "bar",
        "period": "One stock pressure. Save worker benefit blue speak",
    },
    {
        "type": "foo",
        "name": "Pamela Farmer",
        "initial_quota": 223,
        "quota_increase": 62,
        "period": "Expect chance or stop hard southern particularly.",
    },
    {
        "type": "bar",
        "name": "Bobby Chandler",
        "initial_quota": 496,
        "quota_increase": 217,
        "period": "Where animal outside.",
    },
    {
        "type": None,
        "name": "Jeffrey Butler",
        "initial_quota": 445,
        "quota_increase": 78,
        "period": "Song child mind. Sit win miss gas as.",
    },
    {
        "type": "cluster_limiter",
        "name": None,
        "initial_quota": 375,
        "quota_increase": 953,
        "period": "Feel husband phone together summer.",
    },
    {
        "type": "cluster_limiter",
        "name": "Jacqueline Allen",
        "initial_quota": None,
        "quota_increase": 277,
        "period": "Whose environmental life food bit young.",
    },
    {
        "type": "cluster_limiter",
        "name": "Matthew Williams",
        "initial_quota": 696,
        "quota_increase": None,
        "period": "Perhaps girl organization ok continue.",
    },
    {
        "type": "cluster_limiter",
        "name": "Shawn Stone",
        "initial_quota": 126,
        "quota_increase": 547,
        "period": None,
    },
    {
        "type": None,
        "name": None,
        "initial_quota": None,
        "quota_increase": None,
        "period": None,
    },
]


@pytest.mark.parametrize("config_dict", incorrect_configurations)
def test_configure_quota_handlers_from_dict_negative_cases(
    config_dict: dict[str, Any],
) -> None:
    """Test the configuration initialization from dictionary with config values."""
    with pytest.raises(ValueError, match="validation error"):
        # try to initialize the app config and load configuration from a Python
        # dictionary
        QuotaLimiterConfiguration(**config_dict)

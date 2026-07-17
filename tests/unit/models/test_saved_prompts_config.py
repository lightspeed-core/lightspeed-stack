"""Unit tests for SavedPromptsConfiguration."""

from typing import Any

import pytest
from pydantic import ValidationError

from lightspeed_stack import constants
from lightspeed_stack.models.config import Configuration, SavedPromptsConfiguration


class TestSavedPromptsConfigurationDefaults:
    """Test cases for default value application."""

    def test_all_defaults_when_no_fields_provided(self) -> None:
        """All fields receive their default values when omitted."""
        config = SavedPromptsConfiguration()
        assert (
            config.max_prompts_per_user == constants.SAVED_PROMPTS_DEFAULT_MAX_PER_USER
        )
        assert (
            config.max_display_name_length
            == constants.SAVED_PROMPTS_DEFAULT_MAX_DISPLAY_NAME_LENGTH
        )
        assert (
            config.max_content_length
            == constants.SAVED_PROMPTS_DEFAULT_MAX_CONTENT_LENGTH
        )

    def test_partial_fields_receive_defaults(self) -> None:
        """Omitted fields get defaults while explicit values are preserved."""
        config = SavedPromptsConfiguration(max_prompts_per_user=10)
        assert config.max_prompts_per_user == 10
        assert (
            config.max_display_name_length
            == constants.SAVED_PROMPTS_DEFAULT_MAX_DISPLAY_NAME_LENGTH
        )
        assert (
            config.max_content_length
            == constants.SAVED_PROMPTS_DEFAULT_MAX_CONTENT_LENGTH
        )


class TestSavedPromptsConfigurationValidValues:
    """Test cases for explicit valid values."""

    def test_explicit_values_within_bounds(self) -> None:
        """Explicit values within bounds are preserved."""
        config = SavedPromptsConfiguration(
            max_prompts_per_user=100,
            max_display_name_length=128,
            max_content_length=5000,
        )
        assert config.max_prompts_per_user == 100
        assert config.max_display_name_length == 128
        assert config.max_content_length == 5000

    def test_exact_upper_bound_values_accepted(self) -> None:
        """Values exactly at the upper bound are accepted."""
        config = SavedPromptsConfiguration(
            max_prompts_per_user=constants.SAVED_PROMPTS_MAX_PER_USER_UPPER_BOUND,
            max_display_name_length=constants.SAVED_PROMPTS_MAX_DISPLAY_NAME_LENGTH_UPPER_BOUND,
            max_content_length=constants.SAVED_PROMPTS_MAX_CONTENT_LENGTH_UPPER_BOUND,
        )
        assert (
            config.max_prompts_per_user
            == constants.SAVED_PROMPTS_MAX_PER_USER_UPPER_BOUND
        )
        assert (
            config.max_display_name_length
            == constants.SAVED_PROMPTS_MAX_DISPLAY_NAME_LENGTH_UPPER_BOUND
        )
        assert (
            config.max_content_length
            == constants.SAVED_PROMPTS_MAX_CONTENT_LENGTH_UPPER_BOUND
        )

    def test_minimum_value_of_one_accepted(self) -> None:
        """The minimum valid value (1) is accepted for all fields."""
        config = SavedPromptsConfiguration(
            max_prompts_per_user=1,
            max_display_name_length=1,
            max_content_length=1,
        )
        assert config.max_prompts_per_user == 1
        assert config.max_display_name_length == 1
        assert config.max_content_length == 1


class TestSavedPromptsConfigurationUpperBoundValidation:
    """Test cases for upper bound validation."""

    def test_max_prompts_per_user_exceeds_upper_bound(self) -> None:
        """Value above upper bound raises ValidationError."""
        with pytest.raises(ValidationError, match="max_prompts_per_user"):
            overloaded_value = constants.SAVED_PROMPTS_MAX_PER_USER_UPPER_BOUND + 1
            SavedPromptsConfiguration(max_prompts_per_user=overloaded_value)

    def test_max_display_name_length_exceeds_upper_bound(self) -> None:
        """Value above DB column limit raises ValidationError."""
        with pytest.raises(ValidationError, match="max_display_name_length"):
            overloaded_value = (
                constants.SAVED_PROMPTS_MAX_DISPLAY_NAME_LENGTH_UPPER_BOUND + 1
            )
            SavedPromptsConfiguration(max_display_name_length=overloaded_value)

    def test_max_content_length_exceeds_upper_bound(self) -> None:
        """Value above upper bound raises ValidationError."""
        with pytest.raises(ValidationError, match="max_content_length"):
            overloaded_value = (
                constants.SAVED_PROMPTS_MAX_CONTENT_LENGTH_UPPER_BOUND + 1
            )
            SavedPromptsConfiguration(max_content_length=overloaded_value)


class TestSavedPromptsConfigurationLowerBoundValidation:
    """Test cases for lower bound validation (PositiveInt rejects zero/negative)."""

    def test_zero_max_prompts_per_user_rejected(self) -> None:
        """Zero is rejected by PositiveInt."""
        with pytest.raises(ValidationError):
            SavedPromptsConfiguration(max_prompts_per_user=0)

    def test_negative_max_prompts_per_user_rejected(self) -> None:
        """Negative values are rejected."""
        with pytest.raises(ValidationError):
            SavedPromptsConfiguration(max_prompts_per_user=-1)

    def test_zero_max_display_name_length_rejected(self) -> None:
        """Zero is rejected by PositiveInt."""
        with pytest.raises(ValidationError):
            SavedPromptsConfiguration(max_display_name_length=0)

    def test_negative_max_display_name_length_rejected(self) -> None:
        """Negative values are rejected."""
        with pytest.raises(ValidationError):
            SavedPromptsConfiguration(max_display_name_length=-5)

    def test_zero_max_content_length_rejected(self) -> None:
        """Zero is rejected by PositiveInt."""
        with pytest.raises(ValidationError):
            SavedPromptsConfiguration(max_content_length=0)

    def test_negative_max_content_length_rejected(self) -> None:
        """Negative values are rejected."""
        with pytest.raises(ValidationError):
            SavedPromptsConfiguration(max_content_length=-100)


class TestSavedPromptsConfigurationExtraFields:  # pylint: disable=too-few-public-methods
    """Test cases for extra field rejection (ConfigurationBase forbids extra)."""

    def test_unknown_field_rejected(self) -> None:
        """Unknown fields are rejected due to extra='forbid'."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            SavedPromptsConfiguration(
                unknown_field=42
            )  # pyright: ignore[reportCallIssue]


def _build_config_dict(**overrides: Any) -> dict[str, Any]:
    """Build a minimal Configuration dict with optional overrides.

    Args:
        **overrides: Keys to override in the base config dict.

    Returns:
        A dict suitable for Configuration(**dict).
    """
    base: dict[str, Any] = {
        "name": "test",
        "service": {"host": "localhost", "port": 8080},
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {},
        "authentication": {"module": "noop"},
        "authorization": {"access_rules": []},
    }
    base.update(overrides)
    return base


class TestSavedPromptsIntegration:  # pylint: disable=too-few-public-methods
    """Test saved_prompts field on the root Configuration class."""

    def test_configuration_has_saved_prompts_with_defaults(self) -> None:
        """Configuration object has saved_prompts with all defaults when omitted."""
        config = Configuration(**_build_config_dict())
        saved_prompts_config = config.model_dump()["saved_prompts"]
        assert (
            saved_prompts_config["max_prompts_per_user"]
            == constants.SAVED_PROMPTS_DEFAULT_MAX_PER_USER
        )
        assert (
            saved_prompts_config["max_display_name_length"]
            == constants.SAVED_PROMPTS_DEFAULT_MAX_DISPLAY_NAME_LENGTH
        )
        assert (
            saved_prompts_config["max_content_length"]
            == constants.SAVED_PROMPTS_DEFAULT_MAX_CONTENT_LENGTH
        )

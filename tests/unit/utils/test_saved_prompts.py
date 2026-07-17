"""Unit tests for saved prompt validation helpers."""

import pytest

from utils.saved_prompts import (
    SavedPromptLimitExceededError,
    SavedPromptValidationError,
    validate_saved_prompt_content,
    validate_saved_prompt_name,
    validate_saved_prompt_quota,
)


class TestValidateSavedPromptQuota:
    """Test cases for validate_saved_prompt_quota."""

    def test_allows_count_below_max(self) -> None:
        """Test create is allowed when current count is below the inclusive max."""
        validate_saved_prompt_quota(49, 50)

    def test_rejects_count_equal_to_max(self) -> None:
        """Test create is rejected when current count equals the inclusive max."""
        with pytest.raises(
            SavedPromptLimitExceededError,
            match=(
                r"Saved prompt limit exceeded: 50 existing prompts, " r"maximum is 50"
            ),
        ):
            validate_saved_prompt_quota(50, 50)

    def test_rejects_count_above_max(self) -> None:
        """Test create is rejected when current count is above the max."""
        with pytest.raises(
            SavedPromptLimitExceededError,
            match=(
                r"Saved prompt limit exceeded: 51 existing prompts, " r"maximum is 50"
            ),
        ):
            validate_saved_prompt_quota(51, 50)

    def test_rejects_when_max_is_zero(self) -> None:
        """Test max_prompts_per_user of 0 rejects even a zero current count."""
        with pytest.raises(
            SavedPromptLimitExceededError,
            match=(
                r"Saved prompt limit exceeded: 0 existing prompts, " r"maximum is 0"
            ),
        ):
            validate_saved_prompt_quota(0, 0)


class TestValidateSavedPromptName:
    """Test cases for validate_saved_prompt_name."""

    def test_valid_name_returns_stripped_value(self) -> None:
        """Test valid name is accepted and returned stripped."""
        assert (
            validate_saved_prompt_name("  my prompt  ", max_display_name_length=10)
            == "my prompt"
        )

    def test_empty_name_rejected(self) -> None:
        """Test empty name raises SavedPromptValidationError."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt name must not be empty",
        ):
            validate_saved_prompt_name("", max_display_name_length=10)

    def test_spaces_only_name_rejected(self) -> None:
        """Test spaces-only name raises SavedPromptValidationError."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt name must not be empty",
        ):
            validate_saved_prompt_name("   ", max_display_name_length=10)

    def test_mixed_whitespace_only_name_rejected(self) -> None:
        """Test name of only spaces/newlines/tabs is rejected."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt name must not be empty",
        ):
            validate_saved_prompt_name("   \n\t  ", max_display_name_length=10)

    def test_name_at_exact_max_length_accepted(self) -> None:
        """Test name of exactly max_display_name_length is accepted."""
        assert (
            validate_saved_prompt_name("abcdefghij", max_display_name_length=10)
            == "abcdefghij"
        )

    def test_name_longer_than_max_rejected(self) -> None:
        """Test name exceeding max_display_name_length is rejected."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt name length 11 exceeds maximum 10",
        ):
            validate_saved_prompt_name("abcdefghijk", max_display_name_length=10)

    def test_name_rejected_when_max_length_is_zero(self) -> None:
        """Test max_display_name_length of 0 rejects any non-empty name."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt name length 1 exceeds maximum 0",
        ):
            validate_saved_prompt_name("a", max_display_name_length=0)

    def test_unicode_emoji_name_within_length_accepted(self) -> None:
        """Test unicode/emoji name within length is accepted."""
        assert (
            validate_saved_prompt_name("🔥 tip", max_display_name_length=10) == "🔥 tip"
        )


class TestValidateSavedPromptContent:
    """Test cases for validate_saved_prompt_content."""

    def test_valid_content_accepted(self) -> None:
        """Test non-empty content within the max length is accepted."""
        validate_saved_prompt_content(
            "do something useful",
            max_content_length=50,
        )

    def test_empty_content_rejected(self) -> None:
        """Test empty content raises SavedPromptValidationError."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt content must not be empty",
        ):
            validate_saved_prompt_content("", max_content_length=50)

    def test_spaces_only_content_rejected(self) -> None:
        """Test spaces-only content raises SavedPromptValidationError."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt content must not be empty",
        ):
            validate_saved_prompt_content("   ", max_content_length=50)

    def test_mixed_whitespace_only_content_rejected(self) -> None:
        """Test content of only spaces/newlines/tabs is rejected."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt content must not be empty",
        ):
            validate_saved_prompt_content("   \n\t  ", max_content_length=50)

    def test_non_blank_content_with_whitespace_accepted(self) -> None:
        """Test content with leading/trailing whitespace is accepted when non-blank."""
        validate_saved_prompt_content(
            "  keep my spaces  ",
            max_content_length=50,
        )

    def test_content_at_exact_max_length_accepted(self) -> None:
        """Test content of exactly max_content_length is accepted."""
        validate_saved_prompt_content("123456789012", max_content_length=12)

    def test_content_longer_than_max_rejected(self) -> None:
        """Test content exceeding max_content_length is rejected on original length."""
        # Leading spaces count toward length; strip would be under max but original is not.
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt content length 14 exceeds maximum 12",
        ):
            validate_saved_prompt_content(
                "  1234567890  ",
                max_content_length=12,
            )

    def test_content_rejected_when_max_length_is_zero(self) -> None:
        """Test max_content_length of 0 rejects any non-empty content."""
        with pytest.raises(
            SavedPromptValidationError,
            match="Saved prompt content length 1 exceeds maximum 0",
        ):
            validate_saved_prompt_content("a", max_content_length=0)

"""Unit tests for CompactionConfiguration and its placement on Configuration."""

import pytest
from pydantic import ValidationError

from models.config import CompactionConfiguration, Configuration


def test_default_values() -> None:
    """Default-construct CompactionConfiguration matches the spec defaults.

    Defaults come from the conversation-compaction spec doc — disabled,
    70% trigger, 4096 token floor, 4 buffer turns, 30% max buffer.
    """
    config = CompactionConfiguration()
    assert config.enabled is False
    assert config.threshold_ratio == 0.7
    assert config.token_floor == 4096
    assert config.buffer_turns == 4
    assert config.buffer_max_ratio == 0.3
    assert config.summary_prompt is None


def test_enabled_can_be_turned_on() -> None:
    """The enabled master switch is configurable."""
    config = CompactionConfiguration(enabled=True)
    assert config.enabled is True


def test_threshold_ratio_accepts_boundary_values() -> None:
    """threshold_ratio accepts 0.0 and 1.0 inclusively."""
    assert CompactionConfiguration(threshold_ratio=0.0).threshold_ratio == 0.0
    assert CompactionConfiguration(threshold_ratio=1.0).threshold_ratio == 1.0


def test_threshold_ratio_rejects_negative() -> None:
    """threshold_ratio below 0 is rejected."""
    with pytest.raises(ValueError, match="threshold_ratio must be between 0.0 and 1.0"):
        CompactionConfiguration(threshold_ratio=-0.1)


def test_threshold_ratio_rejects_above_one() -> None:
    """threshold_ratio above 1 is rejected."""
    with pytest.raises(ValueError, match="threshold_ratio must be between 0.0 and 1.0"):
        CompactionConfiguration(threshold_ratio=1.1)


def test_buffer_max_ratio_boundary_values() -> None:
    """buffer_max_ratio accepts 0.0 and 1.0 inclusively."""
    assert CompactionConfiguration(buffer_max_ratio=0.0).buffer_max_ratio == 0.0
    assert CompactionConfiguration(buffer_max_ratio=1.0).buffer_max_ratio == 1.0


def test_buffer_max_ratio_rejects_negative() -> None:
    """buffer_max_ratio below 0 is rejected."""
    with pytest.raises(
        ValueError, match="buffer_max_ratio must be between 0.0 and 1.0"
    ):
        CompactionConfiguration(buffer_max_ratio=-0.05)


def test_buffer_max_ratio_rejects_above_one() -> None:
    """buffer_max_ratio above 1 is rejected."""
    with pytest.raises(
        ValueError, match="buffer_max_ratio must be between 0.0 and 1.0"
    ):
        CompactionConfiguration(buffer_max_ratio=1.5)


def test_token_floor_rejects_negative() -> None:
    """token_floor is NonNegativeInt and rejects negatives."""
    with pytest.raises(ValueError):
        CompactionConfiguration(token_floor=-1)


def test_buffer_turns_rejects_negative() -> None:
    """buffer_turns is NonNegativeInt and rejects negatives."""
    with pytest.raises(ValueError):
        CompactionConfiguration(buffer_turns=-1)


def test_token_floor_zero_is_allowed() -> None:
    """A zero token floor is allowed — caller may want pure ratio trigger."""
    assert CompactionConfiguration(token_floor=0).token_floor == 0


def test_buffer_turns_zero_is_allowed() -> None:
    """Zero buffer turns are allowed — caller may want full summarization."""
    assert CompactionConfiguration(buffer_turns=0).buffer_turns == 0


@pytest.mark.parametrize(
    "summary_prompt",
    ["Summarize for support:\n{messages}", "Keep {{literal}} braces.\n{messages}"],
)
def test_summary_prompt_accepts_messages_placeholder(summary_prompt: str) -> None:
    """A prompt whose only replacement field is {messages} is kept unchanged."""
    config = CompactionConfiguration.model_validate({"summary_prompt": summary_prompt})
    assert config.summary_prompt == summary_prompt


@pytest.mark.parametrize(
    ("summary_prompt", "message"),
    [
        ("Summarize the conversation.", "must contain the {messages} placeholder"),
        ("", "must contain the {messages} placeholder"),
        ("{messages} about {product}", "no other replacement field"),
        ("{messages:.100}", "no other replacement field"),
        ("{messages!r}", "no other replacement field"),
        ("{messages", "not a valid format string"),
    ],
)
def test_summary_prompt_rejects_invalid_template(
    summary_prompt: str, message: str
) -> None:
    """A prompt without {messages}, or with any other field, fails to load."""
    with pytest.raises(ValidationError, match=message):
        CompactionConfiguration.model_validate({"summary_prompt": summary_prompt})


def test_rejects_unknown_field() -> None:
    """Unknown fields are forbidden via ConfigurationBase's extra='forbid'."""
    with pytest.raises(ValueError):
        CompactionConfiguration(unknown_field=True)  # type: ignore[call-arg]


def test_root_configuration_has_compaction_field() -> None:
    """The root Configuration declares a `compaction` field typed as
    CompactionConfiguration with a default-factory that produces a
    fresh CompactionConfiguration with the spec defaults."""
    field_info = Configuration.model_fields.get("compaction")
    assert field_info is not None, "Configuration must declare a compaction field"
    assert field_info.annotation is CompactionConfiguration

    # default_factory must produce a CompactionConfiguration with disabled
    # state — sanity check that the wiring isn't accidentally swapping in
    # an enabled-by-default instance.
    factory = field_info.default_factory
    assert factory is not None
    default = factory()  # type: ignore[call-arg]
    assert isinstance(default, CompactionConfiguration)
    assert default.enabled is False

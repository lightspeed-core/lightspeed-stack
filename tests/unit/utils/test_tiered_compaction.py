"""Unit tests for utils/tiered_compaction."""

from typing import Optional

import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai_harness.compaction import (
    ClampOversizedMessages,
    ClearToolResults,
    SummarizingCompaction,
    TieredCompaction,
)

from constants import DEFAULT_CONTEXT_WINDOW
from models.config import CompactionConfiguration
from utils.tiered_compaction import CLAMP_MAX_PART_TOKENS, build_tiered_compaction
from utils.token_estimator import estimate_tokens

ENABLED = CompactionConfiguration(
    enabled=True, threshold_ratio=0.5, buffer_turns=6, buffer_max_ratio=0.25
)


def _build(
    config: CompactionConfiguration = ENABLED,
    model: Optional[TestModel] = None,
    context_window: Optional[int] = None,
    summary_prompt: Optional[str] = None,
) -> TieredCompaction[object]:
    """Build the capability for an enabled configuration and assert it exists."""
    compaction = build_tiered_compaction(
        config, model or TestModel(), context_window, summary_prompt
    )
    assert compaction is not None
    return compaction


def _summarizer(compaction: TieredCompaction[object]) -> SummarizingCompaction[object]:
    """Return the summarizing tier, which the builder puts last."""
    summarizer = compaction.tiers[-1]
    assert isinstance(summarizer, SummarizingCompaction)
    return summarizer


def test_disabled_configuration_builds_nothing() -> None:
    """A disabled configuration yields no capability, whatever else is passed."""
    config = CompactionConfiguration(enabled=False)
    assert build_tiered_compaction(config, TestModel(), 128_000, "{messages}") is None


def test_tiers_come_in_fixed_order() -> None:
    """Clamp, then clear tool results, then summarize."""
    tiers = _build().tiers
    assert [type(tier) for tier in tiers] == [
        ClampOversizedMessages,
        ClearToolResults,
        SummarizingCompaction,
    ]
    assert isinstance(tiers[0], ClampOversizedMessages)
    assert tiers[0].max_part_tokens == CLAMP_MAX_PART_TOKENS


@pytest.mark.parametrize("context_window", [None, 32_000])
def test_threshold_and_context_window_mapping(context_window: Optional[int]) -> None:
    """threshold_ratio becomes target_fraction; the window passes through."""
    compaction = _build(context_window=context_window)
    assert compaction.target_fraction == 0.5
    assert compaction.target_tokens is None
    assert compaction.context_window == context_window
    assert compaction.fallback_context_window == DEFAULT_CONTEXT_WINDOW


@pytest.mark.parametrize(
    ("context_window", "expected_keep_tokens"),
    [(None, None), (10_000, 2_500), (999, 249)],
)
def test_summarizing_tier_mapping(
    context_window: Optional[int], expected_keep_tokens: Optional[int]
) -> None:
    """buffer_turns and buffer_max_ratio map onto the summarizing tier."""
    model = TestModel()
    summarizer = _summarizer(_build(model=model, context_window=context_window))
    assert summarizer.model is model
    assert summarizer.keep_messages == 6
    assert summarizer.keep_tokens == expected_keep_tokens
    assert summarizer.incremental
    assert summarizer.preserve_first_user_message
    assert summarizer.keep_user_messages


def test_estimate_tokens_is_the_tokenizer_everywhere() -> None:
    """The orchestrator and every tier count tokens with estimate_tokens."""
    compaction = _build(context_window=32_000)
    assert compaction.tokenizer is estimate_tokens
    for tier in compaction.tiers:
        assert isinstance(
            tier, (ClampOversizedMessages, ClearToolResults, SummarizingCompaction)
        )
        assert tier.tokenizer is estimate_tokens


def test_token_floor_is_ignored() -> None:
    """Builds that differ only in token_floor are identical."""
    model = TestModel()
    low = ENABLED.model_copy(update={"token_floor": 0})
    high = ENABLED.model_copy(update={"token_floor": 100_000})
    assert _build(low, model, 32_000) == _build(high, model, 32_000)


def test_zero_threshold_ratio_is_rejected() -> None:
    """The harness cannot compact at a zero fraction of the window."""
    config = ENABLED.model_copy(update={"threshold_ratio": 0.0})
    with pytest.raises(ValueError, match="target_fraction"):
        build_tiered_compaction(config, TestModel())


def test_default_summary_prompt_is_kept() -> None:
    """Without a custom prompt the harness default stays in place."""
    default = SummarizingCompaction[object](max_messages=1).summary_prompt
    assert _summarizer(_build()).summary_prompt == default


@pytest.mark.parametrize(
    "summary_prompt",
    ["Summarize for support:\n{messages}", "Keep {{literal}} braces.\n{messages}"],
)
def test_custom_summary_prompt_is_used(summary_prompt: str) -> None:
    """A prompt whose only placeholder is {messages} replaces the default."""
    summarizer = _summarizer(_build(summary_prompt=summary_prompt))
    assert summarizer.summary_prompt == summary_prompt


@pytest.mark.parametrize(
    "summary_prompt",
    [
        "Summarize the conversation.",
        "",
        "{messages} about {product}",
        "{messages:.100}",
        "{messages!r}",
        "{messages",
    ],
)
def test_invalid_summary_prompt_is_rejected(summary_prompt: str) -> None:
    """A prompt without {messages}, or with any other field, is rejected."""
    with pytest.raises(ValueError, match="summary_prompt"):
        build_tiered_compaction(ENABLED, TestModel(), summary_prompt=summary_prompt)

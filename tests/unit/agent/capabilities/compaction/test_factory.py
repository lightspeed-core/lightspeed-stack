"""Unit tests for compaction capability construction."""

from types import SimpleNamespace

import pytest
from pydantic_ai_harness.compaction import (
    ClampOversizedMessages,
    ClearToolResults,
    SummarizingCompaction,
    TieredCompaction,
)
from pytest_mock import MockerFixture

import constants
from agent.capabilities.compaction.factory import CompactionFactory
from agent.types.settings import CompactionSettings
from models.config import CompactionConfiguration
from providers.inference.errors import (
    ModelNotAvailableError,
    ModelTypeNotSupportedError,
    ProviderNotFoundError,
)
from utils.token_estimator import estimate_tokens


def _install(
    mocker: MockerFixture,
    *,
    summary_prompt: str | None = None,
    buffer_turns: int = 2,
    threshold_ratio: float = 0.8,
) -> MockerFixture:
    """Patch compaction configuration and model resolution."""
    mocker.patch(
        "agent.capabilities.compaction.factory.configuration",
        SimpleNamespace(
            compaction=CompactionConfiguration(
                enabled=True,
                threshold_ratio=threshold_ratio,
                buffer_turns=buffer_turns,
                buffer_max_ratio=0.25,
                summary_prompt=summary_prompt,
            )
        ),
    )
    registry = mocker.Mock()
    mocker.patch(
        "agent.capabilities.compaction.factory.ProviderRegistry",
        return_value=registry,
    )
    return registry


def test_disabled_compaction_builds_nothing(mocker: MockerFixture) -> None:
    """Disabled settings do not resolve a summarizer model."""
    registry = _install(mocker)

    assert (
        CompactionFactory.build_capability(
            CompactionSettings(enabled=False, provider="openai", model="gpt")
        )
        is None
    )

    registry.resolve_model_instance.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        ProviderNotFoundError("openai"),
        ModelNotAvailableError("gpt", "llm", "openai"),
        ModelTypeNotSupportedError("llm", "openai"),
    ],
)
def test_unresolved_summarizer_builds_nothing(
    mocker: MockerFixture, error: Exception
) -> None:
    """A summarizer that cannot be resolved produces no capability."""
    registry = _install(mocker)
    registry.resolve_model_instance.side_effect = error

    assert (
        CompactionFactory.build_capability(
            CompactionSettings(enabled=True, provider="openai", model="gpt")
        )
        is None
    )


def test_builds_tiered_compaction_from_configuration(mocker: MockerFixture) -> None:
    """Tier thresholds and the summarizer come from compaction configuration."""
    model = mocker.Mock()
    registry = _install(mocker, buffer_turns=2, threshold_ratio=0.8)
    registry.resolve_model_instance.return_value = model

    capability = CompactionFactory.build_capability(
        CompactionSettings(enabled=True, provider="openai", model="gpt")
    )

    assert isinstance(capability, TieredCompaction)
    registry.resolve_model_instance.assert_called_once_with("llm", "openai", "gpt")
    assert capability.target_fraction == 0.8
    assert capability.context_window is None
    assert capability.fallback_context_window == constants.DEFAULT_CONTEXT_WINDOW
    assert capability.tokenizer is estimate_tokens

    clamp, clear, summarizer = capability.tiers
    assert isinstance(clamp, ClampOversizedMessages)
    assert clamp.max_part_tokens == 50000
    assert clamp.tokenizer is estimate_tokens
    assert isinstance(clear, ClearToolResults)
    assert clear.max_tokens == 1
    assert clear.tokenizer is estimate_tokens
    assert isinstance(summarizer, SummarizingCompaction)
    assert summarizer.model is model
    assert summarizer.max_messages == 1
    assert summarizer.keep_messages == 2
    assert summarizer.keep_tokens is None
    assert summarizer.tokenizer is estimate_tokens
    assert summarizer.incremental is True
    assert summarizer.preserve_first_user_message is True
    assert summarizer.keep_user_messages is True
    default_prompt = SummarizingCompaction.__dataclass_fields__[
        "summary_prompt"
    ].default
    assert summarizer.summary_prompt == default_prompt


def test_custom_summary_prompt_replaces_the_default(mocker: MockerFixture) -> None:
    """A configured summary prompt is copied onto the summarizer."""
    registry = _install(mocker, summary_prompt="Summarize\n{messages}")
    registry.resolve_model_instance.return_value = mocker.Mock()

    capability = CompactionFactory.build_capability(
        CompactionSettings(enabled=True, provider="openai", model="gpt")
    )

    assert isinstance(capability, TieredCompaction)
    summarizer = capability.tiers[2]
    assert isinstance(summarizer, SummarizingCompaction)
    assert summarizer.summary_prompt == "Summarize\n{messages}"

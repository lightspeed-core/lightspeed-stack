"""Unit tests for compaction capability construction."""

from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture, MockType

from agent.capabilities.compaction.factory import CompactionFactory
from agent.types.settings import CompactionSettings
from models.config import CompactionConfiguration, InferenceConfiguration
from providers.inference.errors import (
    ModelNotAvailableError,
    ModelTypeNotSupportedError,
    ProviderNotFoundError,
)

INFERENCE = InferenceConfiguration(default_provider="openai", default_model="gpt")


def _install(
    mocker: MockerFixture,
    compaction: CompactionConfiguration | None = None,
) -> tuple[MockType, MockType]:
    """Patch configuration, model resolution, and the tiered compaction builder."""
    config = compaction or CompactionConfiguration(enabled=True)
    mocker.patch(
        "agent.capabilities.compaction.factory.configuration",
        SimpleNamespace(compaction=config, inference=INFERENCE),
    )
    registry = mocker.Mock()
    mocker.patch(
        "agent.capabilities.compaction.factory.ProviderRegistry",
        return_value=registry,
    )
    builder = mocker.patch(
        "agent.capabilities.compaction.factory.build_tiered_compaction",
    )
    return registry, builder


def test_disabled_compaction_builds_nothing(mocker: MockerFixture) -> None:
    """Disabled settings do not resolve a summarizer or build a capability."""
    registry, builder = _install(mocker)

    assert (
        CompactionFactory.build_capability(
            CompactionSettings(enabled=False, provider="openai", model="gpt")
        )
        is None
    )

    registry.resolve_model_instance.assert_not_called()
    builder.assert_not_called()


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
    registry, builder = _install(mocker)
    registry.resolve_model_instance.side_effect = error

    assert (
        CompactionFactory.build_capability(
            CompactionSettings(enabled=True, provider="openai", model="gpt")
        )
        is None
    )

    builder.assert_not_called()


def test_resolved_model_is_passed_to_the_tiered_builder(
    mocker: MockerFixture,
) -> None:
    """The compaction config, the resolved model and the context window reach the builder.

    The window is resolved for the summarizer model (LCORE-4764) and the
    factory returns whatever the builder produces.
    """
    compaction = CompactionConfiguration(
        enabled=True,
        threshold_ratio=0.8,
        buffer_turns=2,
        summary_prompt="Summarize\n{messages}",
    )
    registry, builder = _install(mocker, compaction)
    resolver = mocker.patch(
        "agent.capabilities.compaction.factory.resolve_context_window",
        return_value=128_000,
    )
    model = mocker.Mock()
    registry.resolve_model_instance.return_value = model
    builder.return_value = mocker.Mock()

    capability = CompactionFactory.build_capability(
        CompactionSettings(enabled=True, provider="openai", model="gpt")
    )

    assert capability is builder.return_value
    registry.resolve_model_instance.assert_called_once_with("llm", "openai", "gpt")
    resolver.assert_called_once_with("openai/gpt", INFERENCE)
    builder.assert_called_once_with(compaction, model, 128_000)


def test_settings_without_provider_and_model_leave_the_window_to_the_harness(
    mocker: MockerFixture,
) -> None:
    """With no provider and model to look up, the builder gets no window."""
    registry, builder = _install(mocker)
    resolver = mocker.patch(
        "agent.capabilities.compaction.factory.resolve_context_window"
    )
    registry.resolve_model_instance.return_value = mocker.Mock()

    CompactionFactory.build_capability(CompactionSettings(enabled=True))

    resolver.assert_not_called()
    builder.assert_called_once()
    assert builder.call_args.args[2] is None

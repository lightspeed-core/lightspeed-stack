"""Unit tests for compaction settings built from a query."""

from types import SimpleNamespace

from pytest_mock import MockerFixture

from agent.types.settings.compaction import CompactionSettings
from models.api.requests import QueryRequest
from models.config import CompactionConfiguration, InferenceConfiguration


def _query(
    *,
    provider: str | None = None,
    model: str | None = None,
) -> QueryRequest:
    """Build a query with optional provider and model overrides."""
    return QueryRequest(
        query="What is Kubernetes?",
        provider=provider,
        model=model,
    )


def _install(
    mocker: MockerFixture,
    *,
    enabled: bool,
    default_provider: str = "openai",
    default_model: str = "default-model",
) -> None:
    """Point compaction settings at a fixed inference and compaction config."""
    mocker.patch(
        "agent.types.settings.compaction.configuration",
        SimpleNamespace(
            inference=InferenceConfiguration(
                default_provider=default_provider,
                default_model=default_model,
            ),
            compaction=CompactionConfiguration(enabled=enabled),
        ),
    )


def test_request_provider_and_model_are_used(mocker: MockerFixture) -> None:
    """An explicit query provider and model select the summarizer."""
    _install(mocker, enabled=True)

    settings = CompactionSettings.from_query_request(
        _query(provider="watsonx", model="granite")
    )

    assert settings == CompactionSettings(
        provider="watsonx",
        model="granite",
        enabled=True,
    )


def test_omitted_provider_and_model_use_inference_defaults(
    mocker: MockerFixture,
) -> None:
    """Blank query values fall back to the configured inference defaults."""
    _install(mocker, enabled=False)

    settings = CompactionSettings.from_query_request(_query(provider="", model=""))

    assert settings.provider == "openai"
    assert settings.model == "default-model"
    assert settings.enabled is False

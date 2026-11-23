"""Unit tests for functions defined in metrics/utils.py."""

from collections.abc import Generator

import pytest
from pytest_mock import MockerFixture

from metrics.utils import setup_model_metrics
from providers.inference.catalog import CatalogModel
from providers.inference.registry import ProviderRegistry
from tests.unit.providers.inference._helpers import make_fake_provider
from utils.types import Singleton


@pytest.fixture(autouse=True)
def _reset_provider_registry() -> Generator[None, None, None]:
    """Reset the singleton registry between metric tests."""
    # pylint: disable=protected-access
    Singleton._instances.pop(ProviderRegistry, None)
    yield
    Singleton._instances.pop(ProviderRegistry, None)
    # pylint: enable=protected-access


def _llm_model(name: str) -> CatalogModel:
    """Create a minimal LLM catalog model."""
    return CatalogModel(
        name=name,
        provider_model_id=f"provider-{name}",
        model_type="llm",
    )


def _embedding_model(name: str) -> CatalogModel:
    """Create a minimal embedding catalog model."""
    return CatalogModel(
        name=name,
        provider_model_id=f"provider-{name}",
        model_type="embedding",
    )


@pytest.mark.asyncio
async def test_setup_model_metrics_from_registry(mocker: MockerFixture) -> None:
    """Test that setup_model_metrics populates gauges from registry catalog."""
    mocker.patch(
        "metrics.utils.configuration.inference.default_provider",
        "provider-a",
    )
    mocker.patch(
        "metrics.utils.configuration.inference.default_model",
        "default-llm",
    )

    mock_metric = mocker.patch("metrics.provider_model_configuration")

    # Set up registry with two providers
    registry = ProviderRegistry()
    provider_a = make_fake_provider(
        provider_id="provider-a",
        models=[_llm_model("default-llm"), _llm_model("other-llm")],
    )
    provider_b = make_fake_provider(
        provider_id="provider-b",
        models=[_llm_model("b-llm"), _embedding_model("b-embed")],
    )
    # pylint: disable=protected-access
    registry._providers["provider-a"] = provider_a
    registry._providers["provider-b"] = provider_b
    # pylint: enable=protected-access

    await setup_model_metrics()

    # Embedding models should be excluded; only LLMs get metrics
    assert mock_metric.labels.call_count == 3
    mock_metric.assert_has_calls(
        [
            mocker.call.labels("provider-a", "default-llm"),
            mocker.call.labels().set(1),
            mocker.call.labels("provider-a", "other-llm"),
            mocker.call.labels().set(0),
            mocker.call.labels("provider-b", "b-llm"),
            mocker.call.labels().set(0),
        ],
        any_order=False,
    )


@pytest.mark.asyncio
async def test_setup_model_metrics_no_default(mocker: MockerFixture) -> None:
    """Test that all models get value 0 when no default is configured."""
    mocker.patch(
        "metrics.utils.configuration.inference.default_provider",
        None,
    )
    mocker.patch(
        "metrics.utils.configuration.inference.default_model",
        None,
    )

    mock_metric = mocker.patch("metrics.provider_model_configuration")

    registry = ProviderRegistry()
    provider = make_fake_provider(
        provider_id="my-provider",
        models=[_llm_model("model-x")],
    )
    # pylint: disable=protected-access
    registry._providers["my-provider"] = provider
    # pylint: enable=protected-access

    await setup_model_metrics()

    mock_metric.labels.assert_called_once_with("my-provider", "model-x")
    mock_metric.labels().set.assert_called_once_with(0)

"""Unit tests for the OpenAI inference provider."""

# pylint: disable=redefined-outer-name,protected-access

from typing import Any

import httpx
import pytest
from openai import APIConnectionError, AuthenticationError
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from models.config import OpenAIInferenceProviderEntry
from providers.inference.catalog import CatalogModel
from providers.inference.errors import ModelDiscoveryError, ModelTypeNotSupportedError
from providers.inference.openai.provider import OpenAIInferenceProvider


@pytest.fixture
def provider() -> OpenAIInferenceProvider:
    """Create an OpenAI provider."""
    entry = OpenAIInferenceProviderEntry.model_validate(
        {
            "type": "openai",
            "id": "openai",
            "config": {
                "api_key": "test-key",
                "base_url": "https://example.test/v1",
            },
        }
    )
    return OpenAIInferenceProvider(entry)


def test_build_provider_uses_config(provider: OpenAIInferenceProvider) -> None:
    """Builds a Pydantic AI provider with configured credentials and URL."""
    pai_provider = provider._build_provider()

    assert isinstance(pai_provider, OpenAIProvider)
    assert str(pai_provider.client.base_url).rstrip("/") == "https://example.test/v1"
    assert pai_provider.client.api_key == "test-key"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_id", "expected_type"),
    [
        ("gpt-5.6-luna", "llm"),
        ("text-embedding-3-small", "embedding"),
        ("custom-model", "llm"),
    ],
)
async def test_discover_models_infers_model_types(
    provider: OpenAIInferenceProvider,
    mocker: Any,
    model_id: str,
    expected_type: str,
) -> None:
    """Discovers OpenAI model IDs and applies the model-type inference fallback."""
    response = mocker.MagicMock()
    response.data = [mocker.MagicMock(id=model_id)]

    pai_provider = mocker.MagicMock(spec=OpenAIProvider)
    pai_provider.client.models.list = mocker.AsyncMock(return_value=response)
    provider._provider = pai_provider

    discovered = await provider._discover_models()

    assert len(discovered) == 1
    assert discovered[0].provider_model_id == model_id
    assert discovered[0].model_type == expected_type
    pai_provider.client.models.list.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cause",
    [
        APIConnectionError(
            message="connection failed",
            request=httpx.Request(  # pyright: ignore[reportArgumentType]
                "GET", "https://example.test/v1/models"
            ),
        ),
        AuthenticationError(
            message="unauthorized",
            response=httpx.Response(  # pyright: ignore[reportArgumentType]
                401,
                request=httpx.Request("GET", "https://example.test/v1/models"),
            ),
            body=None,
        ),
    ],
    ids=["connection-error", "authentication-error"],
)
async def test_discover_models_wraps_api_error(
    provider: OpenAIInferenceProvider,
    mocker: Any,
    cause: Exception,
) -> None:
    """OpenAI models.list API subclasses become ModelDiscoveryError."""
    pai_provider = mocker.MagicMock(spec=OpenAIProvider)
    pai_provider.client.models.list = mocker.AsyncMock(side_effect=cause)
    provider._provider = pai_provider

    with pytest.raises(ModelDiscoveryError) as exc_info:
        await provider._discover_models()

    assert exc_info.value.provider_id == "openai"
    assert str(exc_info.value) == "Failed to discover models for provider 'openai'"
    assert exc_info.value.__cause__ is cause


def test_create_llm_uses_openai_responses_model(
    provider: OpenAIInferenceProvider,
) -> None:
    """Creates a Pydantic AI Responses model using the provider model ID."""
    pai_provider = provider._build_provider()
    provider._provider = pai_provider

    model = provider._create_llm(
        CatalogModel(
            name="chat",
            provider_model_id="gpt-5.6-luna",
            model_type="llm",
        )
    )

    assert isinstance(model, OpenAIResponsesModel)
    assert model.model_name == "gpt-5.6-luna"
    assert model.provider is pai_provider


def test_create_embedding_uses_openai_embedding_model(
    provider: OpenAIInferenceProvider,
) -> None:
    """Creates a Pydantic AI embedding model using the provider model ID."""
    pai_provider = provider._build_provider()
    provider._provider = pai_provider

    model = provider._create_embedding(
        CatalogModel(
            name="embed",
            provider_model_id="text-embedding-3-small",
            model_type="embedding",
        )
    )

    assert isinstance(model, OpenAIEmbeddingModel)
    assert model.model_name == "text-embedding-3-small"
    assert model._provider is pai_provider


def test_create_rerank_is_unsupported(
    provider: OpenAIInferenceProvider,
) -> None:
    """Rejects reranking because the OpenAI provider does not support it."""
    with pytest.raises(ModelTypeNotSupportedError) as exc_info:
        provider._create_rerank(
            CatalogModel(
                name="rerank",
                provider_model_id="rerank-model",
                model_type="rerank",
            )
        )

    assert exc_info.value.model_type == "rerank"
    assert exc_info.value.provider_id == "openai"

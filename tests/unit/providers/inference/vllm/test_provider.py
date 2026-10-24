"""Unit tests for the vLLM inference provider."""

# pylint: disable=redefined-outer-name,protected-access

from typing import Any

import pytest
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.vllm import VLLMProvider

from models.config import VllmInferenceProviderEntry
from providers.inference.catalog import CatalogModel
from providers.inference.errors import ModelTypeNotSupportedError
from providers.inference.vllm.provider import VllmInferenceProvider

BASE_URL = "https://example.test/v1"


def _entry(**config: Any) -> VllmInferenceProviderEntry:
    """Build a vLLM provider configuration."""
    return VllmInferenceProviderEntry.model_validate(
        {
            "type": "vllm",
            "id": "vllm",
            "config": {
                "base_url": BASE_URL,
                "api_key": "test-key",
                **config,
            },
        }
    )


@pytest.fixture
def provider() -> VllmInferenceProvider:
    """Create a vLLM provider."""
    return VllmInferenceProvider(_entry())


def test_build_provider_uses_config(provider: VllmInferenceProvider) -> None:
    """Builds a Pydantic AI provider with configured credentials and URL."""
    pai_provider = provider._build_provider()

    assert isinstance(pai_provider, VLLMProvider)
    assert str(pai_provider.client.base_url).rstrip("/") == BASE_URL
    assert pai_provider.client.api_key == "test-key"


def test_build_provider_allows_missing_api_key() -> None:
    """Builds a Pydantic AI provider when no API key is configured."""
    pai_provider = VllmInferenceProvider(_entry(api_key=None))._build_provider()

    assert isinstance(pai_provider, VLLMProvider)
    assert str(pai_provider.client.base_url).rstrip("/") == BASE_URL
    assert pai_provider.client.api_key == "api-key-not-set"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_id", "expected_type"),
    [
        ("gpt-5.6-luna", "llm"),
        ("text-embedding-3-small", "embedding"),
        ("meta-llama/Llama-3.2-1B-Instruct", "llm"),
        ("custom-model", "llm"),
    ],
)
async def test_discover_models_infers_model_types(
    provider: VllmInferenceProvider,
    mocker: Any,
    model_id: str,
    expected_type: str,
) -> None:
    """Discovers vLLM model IDs and applies the model-type inference fallback."""
    response = mocker.MagicMock()
    response.data = [mocker.MagicMock(id=model_id)]

    pai_provider = mocker.MagicMock(spec=VLLMProvider)
    pai_provider.client.models.list = mocker.AsyncMock(return_value=response)
    provider._provider = pai_provider

    discovered = await provider._discover_models()

    assert len(discovered) == 1
    assert discovered[0].provider_model_id == model_id
    assert discovered[0].model_type == expected_type
    pai_provider.client.models.list.assert_awaited_once_with()


def test_create_llm_uses_openai_chat_model(
    provider: VllmInferenceProvider,
) -> None:
    """Creates a Pydantic AI chat model using the provider model ID."""
    pai_provider = provider._build_provider()
    provider._provider = pai_provider

    model = provider._create_llm(
        CatalogModel(
            name="chat",
            provider_model_id="meta-llama/Llama-3.2-1B-Instruct",
            model_type="llm",
        )
    )

    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "meta-llama/Llama-3.2-1B-Instruct"
    assert model.provider is pai_provider


def test_create_embedding_uses_openai_embedding_model(
    provider: VllmInferenceProvider,
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
    provider: VllmInferenceProvider,
) -> None:
    """Rejects reranking because the vLLM provider does not support it."""
    with pytest.raises(ModelTypeNotSupportedError) as exc_info:
        provider._create_rerank(
            CatalogModel(
                name="rerank",
                provider_model_id="rerank-model",
                model_type="rerank",
            )
        )

    assert exc_info.value.model_type == "rerank"
    assert exc_info.value.provider_id == "vllm"


@pytest.mark.parametrize(
    ("model_id", "expected_type"),
    [
        ("text-embedding-3-small", "embedding"),
        ("gpt-5.6-luna", "llm"),
        ("meta-llama/Llama-3.2-1B-Instruct", "llm"),
        ("custom-model", "llm"),
    ],
)
def test_infer_model_type_uses_known_names_with_llm_fallback(
    provider: VllmInferenceProvider,
    model_id: str,
    expected_type: str,
) -> None:
    """Infers embedding from known names; unknown ids (including HF paths) are llm."""
    assert provider._infer_model_type(model_id) == expected_type

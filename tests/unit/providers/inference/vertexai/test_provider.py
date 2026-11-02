"""Unit tests for the Vertex AI inference provider."""

# pylint: disable=redefined-outer-name,protected-access

from typing import Any

import pytest
from google.auth.exceptions import DefaultCredentialsError
from google.genai.errors import ClientError as GoogleGenAIClientError
from pydantic_ai.embeddings.google import GoogleEmbeddingModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google_cloud import GoogleCloudProvider

from models.config import VertexAIInferenceProviderEntry
from providers.inference.catalog import CatalogModel
from providers.inference.errors import ModelDiscoveryError, ModelTypeNotSupportedError
from providers.inference.vertexai.provider import VertexAIInferenceProvider


class _AsyncIter:
    """Minimal async iterator for mocked Vertex model list results."""

    def __init__(self, items: list[Any]) -> None:
        """Store items to yield."""
        self._items = iter(items)

    def __aiter__(self) -> "_AsyncIter":
        """Return self as the async iterator."""
        return self

    async def __anext__(self) -> Any:
        """Yield the next item or stop."""
        try:
            return next(self._items)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@pytest.fixture
def provider() -> VertexAIInferenceProvider:
    """Create a Vertex AI provider."""
    entry = VertexAIInferenceProviderEntry.model_validate(
        {
            "type": "vertexai",
            "id": "vertexai",
            "config": {
                "project": "test-project",
                "location": "us-central1",
            },
        }
    )
    return VertexAIInferenceProvider(entry)


def test_build_provider_uses_config(provider: VertexAIInferenceProvider) -> None:
    """Builds a Pydantic AI Google Cloud provider with project and location."""
    pai_provider = provider._build_provider()

    assert isinstance(pai_provider, GoogleCloudProvider)
    assert pai_provider.name == "google-cloud"
    assert pai_provider.client.vertexai is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("catalog", "expected_type"),
    [
        (
            ("publishers/google/models/gemini-3.5-flash", ["generateContent"]),
            "llm",
        ),
        (
            ("publishers/google/models/text-embedding-005", ["embedContent"]),
            "embedding",
        ),
        (
            ("publishers/meta/models/llama-3.3-70b-instruct-maas", ["generateContent"]),
            "llm",
        ),
        (
            ("custom-model", None),
            "llm",
        ),
    ],
)
async def test_discover_models_keeps_catalog_name(
    provider: VertexAIInferenceProvider,
    mocker: Any,
    catalog: tuple[str, list[str] | None],
    expected_type: str,
) -> None:
    """Keeps catalog resource names and types from known names or actions."""
    name, supported_actions = catalog
    catalog_model = mocker.MagicMock()
    catalog_model.name = name
    catalog_model.supported_actions = supported_actions

    pai_provider = mocker.MagicMock(spec=GoogleCloudProvider)
    pai_provider.client.aio.models.list = mocker.AsyncMock(
        return_value=_AsyncIter([catalog_model])
    )
    provider._provider = pai_provider

    discovered = await provider._discover_models()

    assert len(discovered) == 1
    assert discovered[0].provider_model_id == name
    assert discovered[0].model_type == expected_type
    pai_provider.client.aio.models.list.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cause",
    [
        GoogleGenAIClientError(401, {"error": {"message": "unauthorized"}}),
        DefaultCredentialsError("credentials unavailable"),
    ],
    ids=["genai-client-error", "default-credentials-error"],
)
async def test_discover_models_wraps_foreign_failures(
    provider: VertexAIInferenceProvider,
    mocker: Any,
    cause: Exception,
) -> None:
    """Vertex API/auth subclasses become ModelDiscoveryError."""
    pai_provider = mocker.MagicMock(spec=GoogleCloudProvider)
    pai_provider.client.aio.models.list = mocker.AsyncMock(side_effect=cause)
    provider._provider = pai_provider

    with pytest.raises(ModelDiscoveryError) as exc_info:
        await provider._discover_models()

    assert exc_info.value.provider_id == "vertexai"
    assert str(exc_info.value) == "Failed to discover models for provider 'vertexai'"
    assert exc_info.value.__cause__ is cause


def test_create_llm_uses_google_model(
    provider: VertexAIInferenceProvider,
) -> None:
    """Creates a Pydantic AI Google model using the provider model ID."""
    pai_provider = provider._build_provider()
    provider._provider = pai_provider

    model = provider._create_llm(
        CatalogModel(
            name="chat",
            provider_model_id="gemini-3.5-flash",
            model_type="llm",
        )
    )

    assert isinstance(model, GoogleModel)
    assert model.model_name == "gemini-3.5-flash"
    assert model.provider is pai_provider


def test_create_embedding_uses_google_embedding_model(
    provider: VertexAIInferenceProvider,
) -> None:
    """Creates a Pydantic AI Google embedding model using the provider model ID."""
    pai_provider = provider._build_provider()
    provider._provider = pai_provider

    model = provider._create_embedding(
        CatalogModel(
            name="embed",
            provider_model_id="text-embedding-005",
            model_type="embedding",
        )
    )

    assert isinstance(model, GoogleEmbeddingModel)
    assert model.model_name == "text-embedding-005"
    assert model._provider is pai_provider


def test_create_rerank_is_unsupported(
    provider: VertexAIInferenceProvider,
) -> None:
    """Rejects reranking because the Vertex AI provider does not support it."""
    with pytest.raises(ModelTypeNotSupportedError) as exc_info:
        provider._create_rerank(
            CatalogModel(
                name="rerank",
                provider_model_id="rerank-model",
                model_type="rerank",
            )
        )

    assert exc_info.value.model_type == "rerank"
    assert exc_info.value.provider_id == "vertexai"


@pytest.mark.parametrize(
    ("model_id", "supported_actions", "expected_type"),
    [
        ("text-embedding-005", None, "embedding"),
        ("publishers/google/models/text-embedding-005", None, "embedding"),
        ("gemini-3.5-flash", ["embedContent"], "llm"),
        ("publishers/google/models/gemini-3.5-flash", ["embedContent"], "llm"),
        ("unknown-model", ["generateContent"], "llm"),
        ("unknown-model", ["embedContent"], "embedding"),
        ("unknown-model", None, "llm"),
        ("unknown-model", [], "llm"),
    ],
)
def test_infer_model_type_prefers_known_names_then_actions(
    provider: VertexAIInferenceProvider,
    model_id: str,
    supported_actions: list[str] | None,
    expected_type: str,
) -> None:
    """Prefers PAI known names (including path suffixes), then actions."""
    assert (
        provider._infer_model_type(
            model_id,
            supported_actions=supported_actions,
        )
        == expected_type
    )

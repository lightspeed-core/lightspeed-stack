"""Unit tests for the Azure inference provider."""

# pylint: disable=redefined-outer-name,protected-access

from typing import Any

import httpx
import pytest
from azure.core.exceptions import ClientAuthenticationError
from openai import APIConnectionError, AsyncAzureOpenAI
from pydantic import SecretStr
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.azure import AzureProvider

from models.config import AzureEntraIdConfiguration, AzureInferenceProviderEntry
from providers.inference.azure.provider import AzureInferenceProvider
from providers.inference.catalog import CatalogModel
from providers.inference.errors import ModelDiscoveryError, ModelTypeNotSupportedError

AZURE_ENDPOINT = "https://example.openai.azure.com/"
API_VERSION = "2024-12-01-preview"
ENTRA_SCOPE = "https://cognitiveservices.azure.com/.default"


def _entry(**config: Any) -> AzureInferenceProviderEntry:
    """Build an Azure provider configuration."""
    return AzureInferenceProviderEntry.model_validate(
        {
            "type": "azure",
            "id": "azure",
            "config": {
                "base_url": AZURE_ENDPOINT,
                "api_version": API_VERSION,
                "api_key": "test-key",
                **config,
            },
        }
    )


def _entra_id(
    *,
    tenant_id: str = "tenant",
    client_id: str = "client",
    client_secret: str = "secret",
    scope: str = ENTRA_SCOPE,
) -> AzureEntraIdConfiguration:
    """Build Entra ID configuration for nested or legacy auth."""
    return AzureEntraIdConfiguration(
        tenant_id=SecretStr(tenant_id),
        client_id=SecretStr(client_id),
        client_secret=SecretStr(client_secret),
        scope=scope,
    )


def _patch_entra_dependencies(mocker: Any) -> tuple[Any, Any, Any]:
    """Mock Azure credential, token-provider, and SDK client construction."""
    token_provider = mocker.AsyncMock(return_value="token")
    credential = mocker.patch(
        "providers.inference.azure.provider.ClientSecretCredential"
    )
    get_token_provider = mocker.patch(
        "providers.inference.azure.provider.get_bearer_token_provider",
        return_value=token_provider,
    )
    # PAI AzureProvider(openai_client=...) reads api_key and base_url at init.
    openai_client = mocker.MagicMock(spec=AsyncAzureOpenAI)
    openai_client.api_key = None
    openai_client.base_url = AZURE_ENDPOINT
    client = mocker.patch(
        "providers.inference.azure.provider.AsyncAzureOpenAI",
        return_value=openai_client,
    )
    return credential, get_token_provider, client


@pytest.fixture(autouse=True)
def _default_legacy_entra(mocker: Any) -> None:
    """Leave legacy Entra ID unset unless a test overrides it."""
    mocker.patch(
        "providers.inference.azure.provider.configuration",
        mocker.MagicMock(azure_entra_id=None),
    )


@pytest.fixture
def provider() -> AzureInferenceProvider:
    """Create an Azure provider configured for API-key authentication."""
    return AzureInferenceProvider(_entry())


def test_build_provider_uses_api_key(provider: AzureInferenceProvider) -> None:
    """Builds a Pydantic AI Azure provider with API-key authentication."""
    pai_provider = provider._build_provider()

    assert isinstance(pai_provider, AzureProvider)
    assert isinstance(pai_provider.client, AsyncAzureOpenAI)
    assert pai_provider.client.api_key == "test-key"
    assert pai_provider.client._azure_ad_token_provider is None


@pytest.mark.parametrize(
    ("nested_entra", "legacy_entra"),
    [
        (
            _entra_id(
                tenant_id="nested-tenant",
                client_id="nested-client",
                client_secret="nested-secret",
            ),
            _entra_id(
                tenant_id="legacy-tenant",
                client_id="legacy-client",
                client_secret="legacy-secret",
            ),
        ),
        (
            None,
            _entra_id(
                tenant_id="legacy-tenant",
                client_id="legacy-client",
                client_secret="legacy-secret",
            ),
        ),
    ],
    ids=["nested-takes-precedence", "legacy-fallback"],
)
def test_build_provider_uses_expected_entra_credentials(
    mocker: Any,
    nested_entra: AzureEntraIdConfiguration | None,
    legacy_entra: AzureEntraIdConfiguration,
) -> None:
    """Nested Entra ID takes precedence; legacy configuration is the fallback."""
    mocker.patch(
        "providers.inference.azure.provider.configuration",
        mocker.MagicMock(azure_entra_id=legacy_entra),
    )
    credential, get_token_provider, client = _patch_entra_dependencies(mocker)

    pai_provider = AzureInferenceProvider(
        _entry(entra_id=nested_entra)
    )._build_provider()

    expected = nested_entra or legacy_entra
    assert isinstance(pai_provider, AzureProvider)
    credential.assert_called_once_with(
        tenant_id=expected.tenant_id.get_secret_value(),
        client_id=expected.client_id.get_secret_value(),
        client_secret=expected.client_secret.get_secret_value(),
    )
    get_token_provider.assert_called_once_with(
        credential.return_value,
        expected.scope,
    )
    client.assert_called_once_with(
        azure_endpoint=AZURE_ENDPOINT,
        api_version=API_VERSION,
        azure_ad_token_provider=get_token_provider.return_value,
    )


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
    provider: AzureInferenceProvider,
    mocker: Any,
    model_id: str,
    expected_type: str,
) -> None:
    """Discovers Azure model IDs and applies the model-type inference fallback."""
    response = mocker.MagicMock()
    response.data = [mocker.MagicMock(id=model_id)]

    pai_provider = mocker.MagicMock(spec=AzureProvider)
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
                "GET", f"{AZURE_ENDPOINT}openai/models"
            ),
        ),
        ClientAuthenticationError(message="token acquisition failed"),
    ],
    ids=["connection-error", "entra-auth-error"],
)
async def test_discover_models_wraps_foreign_failures(
    provider: AzureInferenceProvider,
    mocker: Any,
    cause: Exception,
) -> None:
    """OpenAI API subclasses and Entra auth failures become ModelDiscoveryError."""
    pai_provider = mocker.MagicMock(spec=AzureProvider)
    pai_provider.client.models.list = mocker.AsyncMock(side_effect=cause)
    provider._provider = pai_provider

    with pytest.raises(ModelDiscoveryError) as exc_info:
        await provider._discover_models()

    assert exc_info.value.provider_id == "azure"
    assert str(exc_info.value) == "Failed to discover models for provider 'azure'"
    assert exc_info.value.__cause__ is cause


def test_create_llm_uses_openai_responses_model(
    provider: AzureInferenceProvider,
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
    provider: AzureInferenceProvider,
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
    provider: AzureInferenceProvider,
) -> None:
    """Rejects reranking because the Azure provider does not support it."""
    with pytest.raises(ModelTypeNotSupportedError) as exc_info:
        provider._create_rerank(
            CatalogModel(
                name="rerank",
                provider_model_id="rerank-model",
                model_type="rerank",
            )
        )

    assert exc_info.value.model_type == "rerank"
    assert exc_info.value.provider_id == "azure"

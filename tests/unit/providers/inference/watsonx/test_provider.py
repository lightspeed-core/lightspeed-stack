"""Unit tests for the WatsonX inference provider."""

# pylint: disable=redefined-outer-name,protected-access

from typing import Any, Optional

import httpx
import pytest
from openai import APIConnectionError, AuthenticationError
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.models.openai import OpenAIChatModel

from models.config import WatsonxInferenceProviderEntry
from providers.inference.catalog import CatalogModel
from providers.inference.errors import ModelDiscoveryError, ModelTypeNotSupportedError
from providers.inference.watsonx.auth import WatsonxIAMAuth
from providers.inference.watsonx.pai_provider import WatsonxProvider
from providers.inference.watsonx.provider import WatsonxInferenceProvider
from providers.inference.watsonx.specs import (
    FoundationModelFunction,
    FoundationModelResource,
    FoundationModelSpecsResponse,
)

_PROJECT_SETTINGS = {"extra_body": {"project_id": "test-project"}}


@pytest.fixture
def provider() -> WatsonxInferenceProvider:
    """Create a WatsonX provider."""
    entry = WatsonxInferenceProviderEntry.model_validate(
        {
            "type": "watsonx",
            "id": "watsonx",
            "config": {
                "api_key": "test-key",
                "project_id": "test-project",
                "base_url": "https://us-south.ml.cloud.ibm.com",
            },
        }
    )
    return WatsonxInferenceProvider(entry)


def _attach_pai_provider(
    provider: WatsonxInferenceProvider,
    mocker: Any,
) -> Any:
    """Attach a mocked WatsonxProvider to the inference provider."""
    pai_provider = mocker.MagicMock(spec=WatsonxProvider)
    provider._provider = pai_provider
    return pai_provider


def test_build_provider_passes_config(provider: WatsonxInferenceProvider) -> None:
    """Passes configured credentials and base URL into WatsonxProvider."""
    pai_provider = provider._build_provider()

    assert isinstance(pai_provider, WatsonxProvider)
    assert pai_provider.base_url == "https://us-south.ml.cloud.ibm.com"
    assert (
        str(pai_provider.client.base_url).rstrip("/")
        == "https://us-south.ml.cloud.ibm.com/ml/v1"
    )
    assert isinstance(pai_provider.client._client.auth, WatsonxIAMAuth)


@pytest.mark.asyncio
async def test_discover_models_keeps_chat_and_embedding_only(
    provider: WatsonxInferenceProvider,
    mocker: Any,
) -> None:
    """Types from foundation specs and drops unsupported project models."""
    pai_provider = _attach_pai_provider(provider, mocker)
    list_response = mocker.MagicMock()
    list_response.data = [
        mocker.MagicMock(id=model_id)
        for model_id in (
            "ibm/granite-4-h-small",
            "ibm/slate-125m-english-rtrvr-v2",
            "ibm/granite-ttm-512-96-r2",
            "cross-encoder/ms-marco-minilm-l-12-v2",
            "missing-from-specs",
        )
    ]
    pai_provider.client.models.list = mocker.AsyncMock(return_value=list_response)
    mocker.patch.object(
        provider,
        "_list_foundation_model_functions",
        new=mocker.AsyncMock(
            return_value={
                "ibm/granite-4-h-small": frozenset({"text_chat", "text_generation"}),
                "ibm/slate-125m-english-rtrvr-v2": frozenset({"embedding", "rerank"}),
                "ibm/granite-ttm-512-96-r2": frozenset({"time_series_forecast"}),
                "cross-encoder/ms-marco-minilm-l-12-v2": frozenset({"rerank"}),
            }
        ),
    )

    discovered = await provider._discover_models()

    assert [(item.provider_model_id, item.model_type) for item in discovered] == [
        ("ibm/granite-4-h-small", "llm"),
        ("ibm/slate-125m-english-rtrvr-v2", "embedding"),
    ]
    pai_provider.client.models.list.assert_awaited_once_with(
        extra_query={"project_id": "test-project"}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cause",
    [
        APIConnectionError(
            message="connection failed",
            request=httpx.Request(  # pyright: ignore[reportArgumentType]
                "GET", "https://us-south.ml.cloud.ibm.com/ml/v1/models"
            ),
        ),
        AuthenticationError(
            message="unauthorized",
            response=httpx.Response(  # pyright: ignore[reportArgumentType]
                401,
                request=httpx.Request(
                    "GET", "https://us-south.ml.cloud.ibm.com/ml/v1/models"
                ),
            ),
            body=None,
        ),
        httpx.HTTPStatusError(
            "IAM token exchange failed",
            request=httpx.Request("POST", "https://iam.cloud.ibm.com/identity/token"),
            response=httpx.Response(401),
        ),
    ],
    ids=["connection-error", "authentication-error", "iam-http-status-error"],
)
async def test_discover_models_wraps_api_error(
    provider: WatsonxInferenceProvider,
    mocker: Any,
    cause: Exception,
) -> None:
    """WatsonX models.list API subclasses become ModelDiscoveryError."""
    pai_provider = _attach_pai_provider(provider, mocker)
    pai_provider.client.models.list = mocker.AsyncMock(side_effect=cause)
    mocker.patch.object(
        provider,
        "_list_foundation_model_functions",
        new=mocker.AsyncMock(return_value={}),
    )

    with pytest.raises(ModelDiscoveryError) as exc_info:
        await provider._discover_models()

    assert exc_info.value.provider_id == "watsonx"
    assert str(exc_info.value) == "Failed to discover models for provider 'watsonx'"
    assert exc_info.value.__cause__ is cause


@pytest.mark.asyncio
async def test_list_foundation_model_functions(
    provider: WatsonxInferenceProvider,
    mocker: Any,
) -> None:
    """Maps foundation_model_specs resources to model_id -> function ids."""
    pai_provider = _attach_pai_provider(provider, mocker)
    pai_provider.client.get = mocker.AsyncMock(
        return_value=FoundationModelSpecsResponse(
            resources=[
                FoundationModelResource(
                    model_id="ibm/granite-4-h-small",
                    functions=[
                        FoundationModelFunction(id="text_chat"),
                        FoundationModelFunction(id="text_generation"),
                    ],
                ),
                FoundationModelResource(
                    model_id="ibm/slate-125m-english-rtrvr-v2",
                    functions=[
                        FoundationModelFunction(id="embedding"),
                        FoundationModelFunction(id="rerank"),
                    ],
                ),
            ]
        )
    )

    functions_by_id = await provider._list_foundation_model_functions()

    assert functions_by_id == {
        "ibm/granite-4-h-small": frozenset({"text_chat", "text_generation"}),
        "ibm/slate-125m-english-rtrvr-v2": frozenset({"embedding", "rerank"}),
    }
    pai_provider.client.get.assert_awaited_once_with(
        "/foundation_model_specs",
        cast_to=FoundationModelSpecsResponse,
    )


@pytest.mark.parametrize(
    ("create_method", "model_type", "model_id", "model_cls"),
    [
        ("_create_llm", "llm", "ibm/granite-3-8b-instruct", OpenAIChatModel),
        (
            "_create_embedding",
            "embedding",
            "ibm/slate-125m-english-rtrvr",
            OpenAIEmbeddingModel,
        ),
    ],
)
def test_create_injects_project_id(
    provider: WatsonxInferenceProvider,
    create_method: str,
    model_type: str,
    model_id: str,
    model_cls: type,
) -> None:
    """Injects project_id into chat and embedding model settings."""
    provider._provider = provider._build_provider()

    model = getattr(provider, create_method)(
        CatalogModel(
            name="model",
            provider_model_id=model_id,
            model_type=model_type,  # type: ignore[arg-type]
        )
    )

    assert isinstance(model, model_cls)
    assert model.model_name == model_id
    assert model.settings == _PROJECT_SETTINGS


def test_create_rerank_is_unsupported(provider: WatsonxInferenceProvider) -> None:
    """Rejects reranking because the WatsonX provider does not support it."""
    with pytest.raises(ModelTypeNotSupportedError) as exc_info:
        provider._create_rerank(
            CatalogModel(
                name="rerank",
                provider_model_id="rerank-model",
                model_type="rerank",
            )
        )

    assert exc_info.value.model_type == "rerank"
    assert exc_info.value.provider_id == "watsonx"


@pytest.mark.parametrize(
    ("model_id", "expected_type"),
    [
        ("ibm/granite-4-h-small", "llm"),
        ("ibm/slate-125m-english-rtrvr-v2", "embedding"),
        ("ibm/granite-ttm-512-96-r2", None),
        ("missing-from-specs", None),
    ],
)
def test_infer_model_type_from_functions_by_id(
    provider: WatsonxInferenceProvider,
    model_id: str,
    expected_type: Optional[str],
) -> None:
    """Infers llm/embedding from functions_by_id; unsupported ids are None."""
    functions_by_id = {
        "ibm/granite-4-h-small": frozenset({"text_chat", "text_generation"}),
        "ibm/slate-125m-english-rtrvr-v2": frozenset({"embedding", "rerank"}),
        "ibm/granite-ttm-512-96-r2": frozenset({"time_series_forecast"}),
    }

    assert (
        provider._infer_model_type(model_id, functions_by_id=functions_by_id)
        == expected_type
    )

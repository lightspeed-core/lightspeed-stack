"""Shared helpers for inference registry startup integration tests."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml
from botocore.exceptions import ClientError
from openai import APIConnectionError
from pytest_mock import MockerFixture

from configuration import configuration
from providers.inference.types import ProviderType

# Shared logical allow-list / discovery fixtures (not provider-realistic ids).
CHAT = {
    "name": "chat",
    "provider_model_id": "chat-id",
    "model_type": "llm",
}
EMBED = {
    "name": "embed",
    "provider_model_id": "embed-id",
    "model_type": "embedding",
}
RERANK = {
    "name": "rerank",
    "provider_model_id": "rerank-id",
    "model_type": "rerank",
}
MISSING = {
    "name": "missing",
    "provider_model_id": "not-discovered",
    "model_type": "llm",
}
DROPPED_LLM = {
    "name": "dropped",
    "provider_model_id": "dropped-id",
    "model_type": "llm",
}
EXTRA_DISCOVERED_ID = "extra-id"
BEDROCK_PROFILE = {
    "name": "profile",
    "provider_model_id": "profile-id",
    "model_type": "llm",
}
BEDROCK_FOUNDATION_ID = "foundation-id"
BEDROCK_UNSUPPORTED_ID = "image-id"

_SKIP_CONFIGS: dict[ProviderType, dict[str, Any]] = {
    "openai": {"api_key": "test-key", "base_url": "https://api.openai.com/v1"},
    "azure": {
        "api_key": "test-key",
        "base_url": "https://example.openai.azure.com",
        "api_version": "2024-12-01-preview",
    },
    "vertexai": {"project": "test-project", "location": "us-central1"},
    "bedrock": {"region": "us-east-1", "api_key": "test-bearer-token"},
    "watsonx": {
        "api_key": "test-key",
        "project_id": "test-project",
        "base_url": "https://us-south.ml.cloud.ibm.com",
    },
    "vllm": {"base_url": "http://localhost:8000/v1", "api_key": "unused"},
    "sentence_transformers": {"device": "cpu"},
}

PROVIDER_SKIP_DISCOVERY_ENTRIES: dict[ProviderType, dict[str, Any]] = {
    provider_type: {
        "type": provider_type,
        "id": provider_type,
        "skip_model_discovery": True,
        "allowed_models": (
            [EMBED, RERANK] if provider_type == "sentence_transformers" else [CHAT]
        ),
        "config": config,
    }
    for provider_type, config in _SKIP_CONFIGS.items()
}


def write_config(tmp_path: Path, *, inference: dict[str, Any]) -> Path:
    """Write a minimal LCS config with the given inference section."""
    config_path = tmp_path / "lightspeed-stack.yaml"
    payload: dict[str, Any] = {
        "name": "registry-startup-test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "ogx": {
            "use_as_library_client": False,
            "url": "http://localhost:8321",
            "api_key": "xyzzy",
        },
        "user_data_collection": {"feedback_enabled": False},
        "mcp_servers": [],
        "rag": {
            "retrieval": {
                "inline": {"sources": [], "reranker": None},
                "tool": {"sources": []},
            },
        },
        "inference": inference,
    }
    config_path.write_text(yaml.dump(payload), encoding="utf-8")
    return config_path


def load_inference(tmp_path: Path, providers: list[dict[str, Any]]) -> None:
    """Write and load an LCS config whose inference.providers is ``providers``."""
    configuration.load_configuration(
        str(write_config(tmp_path, inference={"providers": providers}))
    )


def provider_entry(
    provider_type: ProviderType,
    *,
    skip_model_discovery: bool = True,
    allowed_models: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Shallow-copy a skip-discovery fixture entry with optional overrides."""
    entry = {**PROVIDER_SKIP_DISCOVERY_ENTRIES[provider_type]}
    entry["skip_model_discovery"] = skip_model_discovery
    if allowed_models is not None:
        entry["allowed_models"] = allowed_models
    return entry


def mock_openai_models_list(
    mocker: MockerFixture,
    *model_ids: str,
    side_effect: Optional[Exception] = None,
) -> Any:
    """Mock the foreign OpenAI ``models.list`` API used during discovery."""
    if side_effect is not None:
        return mocker.patch(
            "openai.resources.models.AsyncModels.list",
            new=mocker.AsyncMock(side_effect=side_effect),
        )

    response = mocker.MagicMock()
    response.data = [mocker.MagicMock(id=model_id) for model_id in model_ids]
    return mocker.patch(
        "openai.resources.models.AsyncModels.list",
        new=mocker.AsyncMock(return_value=response),
    )


def openai_connection_error() -> APIConnectionError:
    """Return a realistic OpenAI transport failure from models.list."""
    return APIConnectionError(
        message="connection failed",
        request=httpx.Request(  # pyright: ignore[reportArgumentType]
            "GET", "https://api.openai.com/v1/models"
        ),
    )


def mock_bedrock_control_plane(
    mocker: MockerFixture,
    foundations: Iterable[dict[str, Any]],
    *,
    profiles: Optional[Iterable[dict[str, Any]]] = None,
    side_effect: Optional[Exception] = None,
) -> Any:
    """Mock Bedrock ListFoundationModels / ListInferenceProfiles for discovery."""
    client = mocker.MagicMock()
    if side_effect is not None:
        client.list_foundation_models.side_effect = side_effect
    else:
        client.list_foundation_models.return_value = {
            "modelSummaries": list(foundations)
        }
    paginator = mocker.MagicMock()
    paginator.paginate.return_value = [
        {"inferenceProfileSummaries": list(profiles or [])}
    ]
    client.get_paginator.return_value = paginator
    return mocker.patch(
        "providers.inference.bedrock.provider.BedrockInferenceProvider"
        "._create_bedrock_client",
        return_value=client,
    )


def bedrock_inference_profile(
    profile_id: str,
    *foundation_model_ids: str,
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Build a ListInferenceProfiles wire summary for discovery mocks."""
    return {
        "inferenceProfileId": profile_id,
        "models": [
            {"modelArn": (f"arn:aws:bedrock:{region}::foundation-model/{model_id}")}
            for model_id in foundation_model_ids
        ],
    }


def bedrock_access_denied_error() -> ClientError:
    """Return a realistic Bedrock ListFoundationModels access failure."""
    return ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "ListFoundationModels",
    )


def bedrock_foundation(
    model_id: str,
    *,
    modalities: Optional[list[str]] = None,
    inference_types: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Build a ListFoundationModels wire summary for discovery mocks."""
    summary: dict[str, Any] = {"modelId": model_id}
    if modalities is not None:
        summary["outputModalities"] = modalities
    if inference_types is not None:
        summary["inferenceTypesSupported"] = inference_types
    return summary


def mock_vertex_models_list(
    mocker: MockerFixture,
    *model_names: str,
) -> Any:
    """Mock Vertex ``aio.models.list``; return the awaitable mock for assertions."""

    class _AsyncIter:
        def __init__(self, items: list[Any]) -> None:
            self._items = items
            self._iter = iter(items)

        def __aiter__(self) -> "_AsyncIter":
            self._iter = iter(self._items)
            return self

        async def __anext__(self) -> Any:
            try:
                return next(self._iter)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    models = []
    for name in model_names:
        model = mocker.MagicMock()
        model.name = name
        model.supported_actions = ["generateContent"]
        models.append(model)

    list_mock = mocker.AsyncMock(return_value=_AsyncIter(models))
    pai_provider = mocker.MagicMock()
    pai_provider.client.aio.models.list = list_mock
    mocker.patch(
        "providers.inference.vertexai.provider.GoogleCloudProvider",
        return_value=pai_provider,
    )
    return list_mock

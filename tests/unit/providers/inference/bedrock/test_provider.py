"""Unit tests for the Bedrock inference provider."""

# pylint: disable=redefined-outer-name,protected-access

from typing import Any, Optional

import pytest
from pydantic_ai.embeddings.bedrock import BedrockEmbeddingModel
from pydantic_ai.models.bedrock import BedrockConverseModel
from pydantic_ai.providers.bedrock import BedrockProvider

from models.config import BedrockInferenceProviderEntry
from providers.inference.bedrock.provider import (
    BedrockInferenceProvider,
    _BearerTokenSession,
)
from providers.inference.catalog import CatalogModel
from providers.inference.errors import ModelTypeNotSupportedError


def _entry(**config: Any) -> BedrockInferenceProviderEntry:
    """Build a Bedrock provider configuration."""
    return BedrockInferenceProviderEntry.model_validate(
        {
            "type": "bedrock",
            "id": "bedrock",
            "config": {
                "region": "us-east-1",
                "profile_name": "test-profile",
                **config,
            },
        }
    )


def _mock_control_plane(
    mocker: Any,
    provider: BedrockInferenceProvider,
    foundations: list[dict[str, Any]],
    profile_pages: Optional[list[list[dict[str, Any]]]] = None,
) -> Any:
    """Stub ListFoundationModels and paginated ListInferenceProfiles."""
    client = mocker.MagicMock()
    client.list_foundation_models.return_value = {"modelSummaries": foundations}
    paginator = mocker.MagicMock()
    paginator.paginate.return_value = [
        {"inferenceProfileSummaries": page} for page in (profile_pages or [])
    ]
    client.get_paginator.return_value = paginator
    mocker.patch.object(provider, "_create_bedrock_client", return_value=client)
    return client


def _foundation_summary(
    model_id: str,
    *,
    inference_types: Optional[list[str]] = None,
    modalities: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Build a ListFoundationModels wire summary dict."""
    summary: dict[str, Any] = {"modelId": model_id}
    if modalities is not None:
        summary["outputModalities"] = modalities
    if inference_types is not None:
        summary["inferenceTypesSupported"] = inference_types
    return summary


def _profile_summary(
    profile_id: str,
    *foundation_model_ids: str,
    region: str = "us-east-1",
) -> dict[str, Any]:
    """Build a ListInferenceProfiles wire summary dict."""
    return {
        "inferenceProfileId": profile_id,
        "models": [
            {"modelArn": (f"arn:aws:bedrock:{region}::foundation-model/{model_id}")}
            for model_id in foundation_model_ids
        ],
    }


def _catalog_model(
    *,
    name: str,
    provider_model_id: str,
    model_type: str,
) -> CatalogModel:
    """Build a catalog model for create_* tests."""
    return CatalogModel(
        name=name,
        provider_model_id=provider_model_id,
        model_type=model_type,  # type: ignore[arg-type]
    )


@pytest.fixture
def provider() -> BedrockInferenceProvider:
    """Create a Bedrock provider with region and bearer credentials."""
    return BedrockInferenceProvider(_entry(api_key="test-bearer-token"))


def test_build_provider_passes_config(
    provider: BedrockInferenceProvider,
    mocker: Any,
) -> None:
    """Builds a Pydantic AI Bedrock provider from configured credentials."""
    built = mocker.MagicMock(spec=BedrockProvider)
    bedrock_provider_cls = mocker.patch(
        "providers.inference.bedrock.provider.BedrockProvider",
        return_value=built,
    )

    pai_provider = provider._build_provider()

    assert pai_provider is built
    bedrock_provider_cls.assert_called_once_with(
        region_name="us-east-1",
        profile_name="test-profile",
        api_key="test-bearer-token",
    )


def test_create_bedrock_client_uses_bearer_session(
    provider: BedrockInferenceProvider,
    mocker: Any,
) -> None:
    """Builds a control-plane client with bearer auth when a token is set."""
    client = mocker.MagicMock()
    session = mocker.MagicMock()
    session.client.return_value = client
    session_cls = mocker.patch(
        "providers.inference.bedrock.provider.boto3.Session",
        return_value=session,
    )

    assert provider._create_bedrock_client() is client

    session_kwargs = session_cls.call_args.kwargs
    assert session_kwargs["region_name"] == "us-east-1"
    assert session_kwargs["profile_name"] == "test-profile"
    assert isinstance(session_kwargs["botocore_session"], _BearerTokenSession)
    assert session_kwargs["botocore_session"].token == "test-bearer-token"
    assert session.client.call_args.args[0] == "bedrock"
    assert session.client.call_args.kwargs["config"].signature_version == "bearer"


def test_create_bedrock_client_uses_sigv4_without_token(
    mocker: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Builds a control-plane client with SigV4 when no bearer token is set."""
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    provider = BedrockInferenceProvider(_entry())
    client = mocker.MagicMock()
    session = mocker.MagicMock()
    session.client.return_value = client
    session_cls = mocker.patch(
        "providers.inference.bedrock.provider.boto3.Session",
        return_value=session,
    )

    assert provider._create_bedrock_client() is client

    session_cls.assert_called_once_with(
        profile_name="test-profile",
        region_name="us-east-1",
        botocore_session=None,
    )
    session.client.assert_called_once_with("bedrock", config=None)


@pytest.mark.asyncio
async def test_discover_models_types_and_skips_by_modality(
    provider: BedrockInferenceProvider,
    mocker: Any,
) -> None:
    """Keeps TEXT as llm and EMBEDDING as embedding; skips other modalities."""
    client = _mock_control_plane(
        mocker,
        provider,
        [
            _foundation_summary(
                "nvidia.nemotron-nano-12b-v2",
                modalities=["TEXT"],
                inference_types=["ON_DEMAND"],
            ),
            _foundation_summary(
                "amazon.titan-embed-text-v2:0",
                modalities=["EMBEDDING"],
                inference_types=["ON_DEMAND"],
            ),
            _foundation_summary(
                "stability.stable-diffusion-xl-v1",
                modalities=["IMAGE"],
                inference_types=["ON_DEMAND"],
            ),
            _foundation_summary("custom-unknown"),
        ],
    )

    discovered = await provider._discover_models()

    assert [(item.provider_model_id, item.model_type) for item in discovered] == [
        ("nvidia.nemotron-nano-12b-v2", "llm"),
        ("amazon.titan-embed-text-v2:0", "embedding"),
    ]
    client.list_foundation_models.assert_called_once_with()
    client.get_paginator.assert_called_once_with("list_inference_profiles")
    client.get_paginator.return_value.paginate.assert_called_once_with(
        typeEquals="SYSTEM_DEFINED"
    )


@pytest.mark.asyncio
async def test_discover_models_remaps_profile_only_and_skips_unusable(
    provider: BedrockInferenceProvider,
    mocker: Any,
) -> None:
    """Keeps on-demand ids, remaps the first profile, and drops unusable models."""
    _mock_control_plane(
        mocker,
        provider,
        [
            _foundation_summary(
                "amazon.nova-pro-v1:0",
                modalities=["TEXT"],
                inference_types=["ON_DEMAND", "INFERENCE_PROFILE"],
            ),
            _foundation_summary(
                "openai.gpt-6-astra",
                modalities=["TEXT"],
                inference_types=["INFERENCE_PROFILE"],
            ),
            _foundation_summary(
                "missing.profile-only",
                modalities=["TEXT"],
                inference_types=["INFERENCE_PROFILE"],
            ),
            _foundation_summary(
                "amazon.nova-pro-v1:0:300k",
                modalities=["TEXT"],
                inference_types=["PROVISIONED"],
            ),
            _foundation_summary(
                "amazon.titan-embed-text-v2:0:8k",
                modalities=["EMBEDDING"],
            ),
        ],
        [[_profile_summary("us.openai.gpt-6-astra", "openai.gpt-6-astra")]],
    )

    discovered = await provider._discover_models()

    assert [(item.provider_model_id, item.model_type) for item in discovered] == [
        ("amazon.nova-pro-v1:0", "llm"),
        ("us.openai.gpt-6-astra", "llm"),
    ]


def test_create_llm_uses_bedrock_converse_model(
    provider: BedrockInferenceProvider,
    mocker: Any,
) -> None:
    """Creates a Bedrock Converse model using the provider model ID."""
    pai_provider = mocker.MagicMock(spec=BedrockProvider)
    provider._provider = pai_provider

    model = provider._create_llm(
        _catalog_model(
            name="chat",
            provider_model_id="anthropic.claude-3-haiku-20240307-v1:0",
            model_type="llm",
        )
    )

    assert isinstance(model, BedrockConverseModel)
    assert model.model_name == "anthropic.claude-3-haiku-20240307-v1:0"
    assert model.provider is pai_provider


def test_create_embedding_uses_bedrock_embedding_model(
    provider: BedrockInferenceProvider,
    mocker: Any,
) -> None:
    """Creates a Bedrock embedding model using the provider model ID."""
    pai_provider = mocker.MagicMock(spec=BedrockProvider)
    provider._provider = pai_provider

    model = provider._create_embedding(
        _catalog_model(
            name="embed",
            provider_model_id="amazon.titan-embed-text-v2:0",
            model_type="embedding",
        )
    )

    assert isinstance(model, BedrockEmbeddingModel)
    assert model.model_name == "amazon.titan-embed-text-v2:0"
    assert model._provider is pai_provider


def test_create_rerank_is_unsupported(
    provider: BedrockInferenceProvider,
) -> None:
    """Rejects reranking because the Bedrock provider does not support it."""
    with pytest.raises(ModelTypeNotSupportedError) as exc_info:
        provider._create_rerank(
            _catalog_model(
                name="rerank",
                provider_model_id="rerank-model",
                model_type="rerank",
            )
        )

    assert exc_info.value.model_type == "rerank"
    assert exc_info.value.provider_id == "bedrock"

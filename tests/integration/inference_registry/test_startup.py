"""Integration tests for inference provider registry startup."""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from configuration import configuration
from providers.inference.bedrock.provider import BedrockInferenceProvider
from providers.inference.errors import ModelDiscoveryError
from providers.inference.openai.provider import OpenAIInferenceProvider
from providers.inference.registry import PROVIDER_CLASSES, ProviderRegistry
from providers.inference.sentence_transformers.provider import (
    SentenceTransformersInferenceProvider,
)
from providers.inference.types import ProviderType
from providers.inference.vertexai.provider import VertexAIInferenceProvider
from providers.inference.vllm.provider import VllmInferenceProvider
from tests.integration.inference_registry._helpers import (
    BEDROCK_FOUNDATION_ID,
    BEDROCK_PROFILE,
    BEDROCK_UNSUPPORTED_ID,
    CHAT,
    DROPPED_LLM,
    EMBED,
    EXTRA_DISCOVERED_ID,
    MISSING,
    PROVIDER_SKIP_DISCOVERY_ENTRIES,
    RERANK,
    bedrock_access_denied_error,
    bedrock_foundation,
    bedrock_inference_profile,
    load_inference,
    mock_bedrock_control_plane,
    mock_openai_models_list,
    mock_vertex_models_list,
    openai_connection_error,
    provider_entry,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_type", sorted(PROVIDER_CLASSES))
async def test_registry_initializes_each_registered_provider_type(
    tmp_path: Path,
    provider_type: ProviderType,
) -> None:
    """Each PROVIDER_CLASSES type initializes from config via skip-discovery."""
    entry = PROVIDER_SKIP_DISCOVERY_ENTRIES[provider_type]
    load_inference(tmp_path, [entry])

    await ProviderRegistry().initialize(configuration.inference)

    registry = ProviderRegistry()
    provider = registry.get_provider(entry["id"])
    assert isinstance(provider, PROVIDER_CLASSES[provider_type])
    assert [
        model.model_dump(exclude={"metadata"}) for model in registry.list_models()
    ] == entry["allowed_models"]


@pytest.mark.asyncio
async def test_registry_skip_discovery_does_not_call_openai_models_list(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """skip_model_discovery=True must not hit the foreign models.list API."""
    list_mock = mock_openai_models_list(mocker, CHAT["provider_model_id"])
    load_inference(tmp_path, [PROVIDER_SKIP_DISCOVERY_ENTRIES["openai"]])

    await ProviderRegistry().initialize(configuration.inference)

    assert [
        model.model_dump(exclude={"metadata"})
        for model in ProviderRegistry().list_models()
    ] == [CHAT]
    list_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_registry_initialize_with_empty_providers_succeeds(
    tmp_path: Path,
) -> None:
    """Empty inference.providers[] leaves an empty but initialized registry."""
    load_inference(tmp_path, [])

    await ProviderRegistry().initialize(configuration.inference)

    assert ProviderRegistry().list_providers() == []
    assert ProviderRegistry().list_models() == []


@pytest.mark.asyncio
async def test_registry_discovery_filters_allow_list_via_base_catalog(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Base ``_load_catalog`` keep/drop logic runs once through OpenAI."""
    list_mock = mock_openai_models_list(
        mocker,
        CHAT["provider_model_id"],
        EMBED["provider_model_id"],
        EXTRA_DISCOVERED_ID,
    )
    load_inference(
        tmp_path,
        [
            provider_entry(
                "openai",
                skip_model_discovery=False,
                allowed_models=[CHAT, EMBED, MISSING],
            )
        ],
    )

    await ProviderRegistry().initialize(configuration.inference)

    registry = ProviderRegistry()
    assert isinstance(registry.get_provider("openai"), OpenAIInferenceProvider)
    assert [model.name for model in registry.list_models()] == [
        CHAT["name"],
        EMBED["name"],
    ]
    assert [model.name for model in registry.list_models(model_type="embedding")] == [
        EMBED["name"]
    ]
    list_mock.assert_awaited()


@pytest.mark.asyncio
async def test_registry_discovery_empty_allow_list_publishes_all_models(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Empty allow-list publishes every discovered model under its wire id."""
    list_mock = mock_openai_models_list(
        mocker,
        CHAT["provider_model_id"],
        EMBED["provider_model_id"],
    )
    load_inference(
        tmp_path,
        [
            provider_entry(
                "openai",
                skip_model_discovery=False,
                allowed_models=[],
            )
        ],
    )

    await ProviderRegistry().initialize(configuration.inference)

    models = ProviderRegistry().list_models()
    assert [(model.name, model.provider_model_id) for model in models] == [
        (CHAT["provider_model_id"], CHAT["provider_model_id"]),
        (EMBED["provider_model_id"], EMBED["provider_model_id"]),
    ]
    list_mock.assert_awaited()


@pytest.mark.asyncio
async def test_registry_vllm_discovery_builds_catalog_from_models_list(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """vLLM discovery uses the OpenAI-compatible models.list through the registry."""
    list_mock = mock_openai_models_list(
        mocker,
        CHAT["provider_model_id"],
        EXTRA_DISCOVERED_ID,
    )
    load_inference(
        tmp_path,
        [
            provider_entry(
                "vllm",
                skip_model_discovery=False,
                allowed_models=[CHAT],
            )
        ],
    )

    await ProviderRegistry().initialize(configuration.inference)

    registry = ProviderRegistry()
    assert isinstance(registry.get_provider("vllm"), VllmInferenceProvider)
    assert [
        model.model_dump(exclude={"metadata"}) for model in registry.list_models()
    ] == [CHAT]
    list_mock.assert_awaited()


@pytest.mark.asyncio
async def test_registry_bedrock_discovery_builds_catalog_from_control_plane(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Bedrock keeps on-demand and profile ids; skips unsupported modalities."""
    mock_bedrock_control_plane(
        mocker,
        [
            bedrock_foundation(
                CHAT["provider_model_id"],
                modalities=["TEXT"],
                inference_types=["ON_DEMAND"],
            ),
            bedrock_foundation(
                EMBED["provider_model_id"],
                modalities=["EMBEDDING"],
                inference_types=["ON_DEMAND"],
            ),
            bedrock_foundation(
                BEDROCK_FOUNDATION_ID,
                modalities=["TEXT"],
                inference_types=["INFERENCE_PROFILE"],
            ),
            bedrock_foundation(
                BEDROCK_UNSUPPORTED_ID,
                modalities=["IMAGE"],
                inference_types=["ON_DEMAND"],
            ),
        ],
        profiles=[
            bedrock_inference_profile(
                BEDROCK_PROFILE["provider_model_id"],
                BEDROCK_FOUNDATION_ID,
            ),
        ],
    )
    load_inference(
        tmp_path,
        [
            provider_entry(
                "bedrock",
                skip_model_discovery=False,
                allowed_models=[CHAT, EMBED, BEDROCK_PROFILE],
            )
        ],
    )

    await ProviderRegistry().initialize(configuration.inference)

    registry = ProviderRegistry()
    assert isinstance(registry.get_provider("bedrock"), BedrockInferenceProvider)
    assert [
        model.model_dump(exclude={"metadata"}) for model in registry.list_models()
    ] == [CHAT, EMBED, BEDROCK_PROFILE]


@pytest.mark.asyncio
async def test_registry_vertex_discovery_keeps_catalog_resource_names(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Vertex discovery keeps discovered model names as provider model ids."""
    list_mock = mock_vertex_models_list(
        mocker,
        CHAT["provider_model_id"],
        EXTRA_DISCOVERED_ID,
    )
    load_inference(
        tmp_path,
        [
            provider_entry(
                "vertexai",
                skip_model_discovery=False,
                allowed_models=[CHAT],
            )
        ],
    )

    await ProviderRegistry().initialize(configuration.inference)

    registry = ProviderRegistry()
    assert isinstance(registry.get_provider("vertexai"), VertexAIInferenceProvider)
    assert [
        model.model_dump(exclude={"metadata"}) for model in registry.list_models()
    ] == [CHAT]
    list_mock.assert_awaited()


@pytest.mark.asyncio
async def test_registry_sentence_transformers_catalog_drops_llm_entries(
    tmp_path: Path,
) -> None:
    """Sentence-transformers catalog override keeps embed/rerank and drops llm."""
    load_inference(
        tmp_path,
        [
            provider_entry(
                "sentence_transformers",
                skip_model_discovery=False,
                allowed_models=[EMBED, RERANK, DROPPED_LLM],
            )
        ],
    )

    await ProviderRegistry().initialize(configuration.inference)

    registry = ProviderRegistry()
    provider = registry.get_provider("sentence_transformers")
    assert isinstance(provider, SentenceTransformersInferenceProvider)
    assert [(model.name, model.model_type) for model in registry.list_models()] == [
        (EMBED["name"], EMBED["model_type"]),
        (RERANK["name"], RERANK["model_type"]),
    ]


@pytest.mark.asyncio
async def test_registry_openai_discovery_failure_aborts_initialization(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """OpenAI models.list transport failure aborts registry initialization."""
    mock_openai_models_list(mocker, side_effect=openai_connection_error())
    load_inference(
        tmp_path,
        [
            provider_entry(
                "openai",
                skip_model_discovery=False,
                allowed_models=[CHAT],
            )
        ],
    )

    with pytest.raises(ModelDiscoveryError) as exc_info:
        await ProviderRegistry().initialize(configuration.inference)

    assert exc_info.value.provider_id == "openai"
    assert ProviderRegistry().list_providers() == []


@pytest.mark.asyncio
async def test_registry_bedrock_discovery_failure_aborts_initialization(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    """Bedrock control-plane AccessDenied aborts registry initialization."""
    mock_bedrock_control_plane(
        mocker,
        [],
        side_effect=bedrock_access_denied_error(),
    )
    load_inference(
        tmp_path,
        [
            provider_entry(
                "bedrock",
                skip_model_discovery=False,
                allowed_models=[CHAT],
            )
        ],
    )

    with pytest.raises(ModelDiscoveryError) as exc_info:
        await ProviderRegistry().initialize(configuration.inference)

    assert exc_info.value.provider_id == "bedrock"
    assert ProviderRegistry().list_providers() == []

"""Unit tests for the ProviderRegistry singleton."""

from collections.abc import Generator
from typing import Any, Optional

import pytest
from pydantic_ai.embeddings import TestEmbeddingModel
from pydantic_ai.models.test import TestModel
from sentence_transformers import CrossEncoder

from models.config import (
    AllowedModel,
    InferenceConfiguration,
    OpenAIInferenceProviderEntry,
    VllmInferenceProviderEntry,
)
from providers.inference.errors import (
    ModelNotAvailableError,
    NoModelConfiguredError,
    ProviderNotFoundError,
)
from providers.inference.registry import PROVIDER_CLASSES, ProviderRegistry
from providers.inference.types import ModelType, ProviderType
from tests.unit.providers.inference._helpers import FakeInferenceProvider
from utils.types import Singleton


@pytest.fixture(autouse=True)
def _reset_registry_and_provider_classes() -> Generator[None, None, None]:
    """Isolate the provider registry and provider classes per test."""
    original = dict(PROVIDER_CLASSES)
    PROVIDER_CLASSES.clear()
    # pylint: disable=protected-access
    Singleton._instances.pop(ProviderRegistry, None)

    yield

    PROVIDER_CLASSES.clear()
    PROVIDER_CLASSES.update(original)
    Singleton._instances.pop(ProviderRegistry, None)
    # pylint: enable=protected-access


def _register_fake(*provider_types: ProviderType) -> None:
    """Register FakeInferenceProvider for the given provider types."""
    for provider_type in provider_types:
        PROVIDER_CLASSES[provider_type] = FakeInferenceProvider


def _openai_entry(
    provider_id: str = "openai",
    *,
    allowed_models: Optional[list[AllowedModel]] = None,
) -> OpenAIInferenceProviderEntry:
    """Build an OpenAI provider entry that skips model discovery."""
    return OpenAIInferenceProviderEntry(
        id=provider_id,
        skip_model_discovery=True,
        allowed_models=(
            allowed_models
            if allowed_models is not None
            else [
                AllowedModel(
                    name="chat",
                    provider_model_id="gpt-4o-mini",
                    model_type="llm",
                ),
                AllowedModel(
                    name="embed",
                    provider_model_id="text-embedding-3-small",
                    model_type="embedding",
                ),
                AllowedModel(
                    name="rerank",
                    provider_model_id="cross-encoder",
                    model_type="rerank",
                ),
            ]
        ),
    )  # pyright: ignore[reportCallIssue]


def _vllm_entry(
    provider_id: str = "vllm",
    *,
    allowed_models: Optional[list[AllowedModel]] = None,
) -> VllmInferenceProviderEntry:
    """Build a vLLM provider entry that skips model discovery."""
    return VllmInferenceProviderEntry(
        id=provider_id,
        skip_model_discovery=True,
        allowed_models=(
            allowed_models
            if allowed_models is not None
            else [
                AllowedModel(
                    name="embed",
                    provider_model_id="text-embedding-3-small",
                    model_type="embedding",
                )
            ]
        ),
    )  # pyright: ignore[reportCallIssue]


def _inference_config(
    *providers: OpenAIInferenceProviderEntry | VllmInferenceProviderEntry,
) -> InferenceConfiguration:
    """Build inference configuration from provider entries."""
    return InferenceConfiguration.model_validate(
        {"providers": [provider.model_dump() for provider in providers]}
    )


def _llm_model(name: str, provider_model_id: str = "gpt-4o") -> AllowedModel:
    """Return an llm allow-list entry with the given local name."""
    return AllowedModel(
        name=name,
        provider_model_id=provider_model_id,
        model_type="llm",
    )


def _embed_only_models() -> list[AllowedModel]:
    """Return an allow-list with embedding models only."""
    return [
        AllowedModel(
            name="embed-only",
            provider_model_id="text-embedding-3-small",
            model_type="embedding",
        )
    ]


def _rerank_only_models() -> list[AllowedModel]:
    """Return an allow-list with rerank models only."""
    return [
        AllowedModel(
            name="rerank-only",
            provider_model_id="cross-encoder",
            model_type="rerank",
        )
    ]


def _patch_inference_defaults(
    mocker: Any,
    *,
    default_model: Optional[str],
    default_provider: Optional[str],
) -> None:
    """Patch resolve.configuration with fixed default provider/model ids."""
    mocker.patch(
        "providers.inference.resolve.configuration",
        mocker.Mock(
            inference=mocker.Mock(
                default_model=default_model,
                default_provider=default_provider,
            )
        ),
    )


def _patch_conversation(
    mocker: Any,
    *,
    last_used_provider: str = "openai",
    last_used_model: str = "conv-chat",
) -> None:
    """Patch conversation lookup used by soft last-used fallback."""
    conversation = mocker.Mock()
    conversation.last_used_provider = last_used_provider
    conversation.last_used_model = last_used_model
    mocker.patch(
        "providers.inference.resolve.retrieve_conversation",
        return_value=conversation,
    )


async def _ready_registry(
    *providers: OpenAIInferenceProviderEntry,
) -> ProviderRegistry:
    """Register FakeInferenceProvider and initialize with the given providers."""
    _register_fake("openai")
    registry = ProviderRegistry()
    await registry.initialize(_inference_config(*providers))
    return registry


@pytest.mark.asyncio
async def test_initialize_registers_configured_providers() -> None:
    """initialize registers a provider for each configured entry."""
    _register_fake("openai", "vllm")
    registry = ProviderRegistry()

    await registry.initialize(_inference_config(_openai_entry(), _vllm_entry()))

    assert [provider.provider_id for provider in registry.list_providers()] == [
        "openai",
        "vllm",
    ]


@pytest.mark.asyncio
async def test_initialize_adds_to_existing_providers() -> None:
    """Repeated initialization adds providers without removing existing ones."""
    _register_fake("openai", "vllm")
    registry = ProviderRegistry()

    await registry.initialize(_inference_config(_openai_entry()))
    await registry.initialize(_inference_config(_vllm_entry()))

    assert [provider.provider_id for provider in registry.list_providers()] == [
        "openai",
        "vllm",
    ]


@pytest.mark.asyncio
async def test_find_provider_returns_provider_or_none() -> None:
    """find_provider returns the provider or None when it is not registered."""
    _register_fake("openai")
    registry = ProviderRegistry()
    await registry.initialize(_inference_config(_openai_entry()))

    provider = registry.find_provider("openai")

    assert provider is not None
    assert provider.provider_id == "openai"
    assert registry.find_provider("missing") is None


@pytest.mark.asyncio
async def test_get_provider_returns_provider_or_raises() -> None:
    """get_provider raises ProviderNotFoundError for an unknown ID."""
    _register_fake("openai")
    registry = ProviderRegistry()
    await registry.initialize(_inference_config(_openai_entry()))

    assert registry.get_provider("openai").provider_id == "openai"

    with pytest.raises(ProviderNotFoundError) as exc_info:
        registry.get_provider("missing")

    assert exc_info.value.provider_id == "missing"


@pytest.mark.asyncio
async def test_list_models_aggregates_providers_and_filters_by_type() -> None:
    """list_models aggregates catalog entries and applies the optional type filter."""
    _register_fake("openai", "vllm")
    registry = ProviderRegistry()
    await registry.initialize(
        _inference_config(
            _openai_entry(
                allowed_models=[
                    AllowedModel(
                        name="chat",
                        provider_model_id="gpt-4o-mini",
                        model_type="llm",
                    ),
                    AllowedModel(
                        name="embed-a",
                        provider_model_id="text-embedding-3-small",
                        model_type="embedding",
                    ),
                ]
            ),
            _vllm_entry(
                allowed_models=[
                    AllowedModel(
                        name="embed-b",
                        provider_model_id="nomic-embed",
                        model_type="embedding",
                    )
                ]
            ),
        )
    )

    assert [model.name for model in registry.list_models()] == [
        "chat",
        "embed-a",
        "embed-b",
    ]
    assert [model.name for model in registry.list_models(model_type="embedding")] == [
        "embed-a",
        "embed-b",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_type", "model_id", "expected_type"),
    [
        ("llm", "chat", TestModel),
        ("embedding", "embed", TestEmbeddingModel),
        ("rerank", "rerank", CrossEncoder),
    ],
)
async def test_resolve_model_instance_explicit_success(
    model_type: ModelType,
    model_id: str,
    expected_type: type,
) -> None:
    """Explicit provider/model ids return the typed model instance."""
    registry = await _ready_registry(_openai_entry())

    instance = registry.resolve_model_instance(
        model_type,
        provider_id="openai",
        model_id=model_id,
    )

    assert isinstance(instance, expected_type)


@pytest.mark.asyncio
async def test_resolve_model_instance_unknown_provider_raises() -> None:
    """Explicit unknown provider_id raises ProviderNotFoundError."""
    registry = await _ready_registry(_openai_entry())

    with pytest.raises(ProviderNotFoundError) as exc_info:
        registry.resolve_model_instance(
            "llm",
            provider_id="missing",
            model_id="chat",
        )

    assert exc_info.value.provider_id == "missing"


@pytest.mark.asyncio
async def test_resolve_model_instance_unknown_model_raises() -> None:
    """Explicit unknown model_id raises ModelNotAvailableError."""
    registry = await _ready_registry(_openai_entry())

    with pytest.raises(ModelNotAvailableError) as exc_info:
        registry.resolve_model_instance(
            "llm",
            provider_id="openai",
            model_id="missing",
        )

    assert exc_info.value.name == "missing"
    assert exc_info.value.model_type == "llm"
    assert exc_info.value.provider_id == "openai"


@pytest.mark.asyncio
async def test_resolve_model_instance_type_mismatch_raises() -> None:
    """Explicit model present under another type raises ModelNotAvailableError."""
    registry = await _ready_registry(_openai_entry())

    with pytest.raises(ModelNotAvailableError) as exc_info:
        registry.resolve_model_instance(
            "embedding",
            provider_id="openai",
            model_id="chat",
        )

    assert exc_info.value.name == "chat"
    assert exc_info.value.model_type == "embedding"


@pytest.mark.asyncio
async def test_resolve_model_instance_prefers_conversation_over_defaults(
    mocker: Any,
) -> None:
    """Conversation last-used wins when both it and configured defaults are available."""
    registry = await _ready_registry(
        _openai_entry(
            allowed_models=[
                _llm_model("conv-chat"),
                _llm_model("default-chat"),
                _llm_model("first-chat"),
            ]
        )
    )
    _patch_conversation(mocker, last_used_model="conv-chat")
    _patch_inference_defaults(
        mocker, default_model="default-chat", default_provider="openai"
    )

    instance = registry.resolve_model_instance("llm", conversation_id="conv-1")

    assert isinstance(instance, TestModel)
    assert instance.model_name == "conv-chat"


@pytest.mark.asyncio
async def test_resolve_model_instance_skips_unavailable_conversation_model(
    mocker: Any,
) -> None:
    """Missing conversation last-used model falls through to configured defaults."""
    registry = await _ready_registry(
        _openai_entry(
            allowed_models=[
                _llm_model("default-chat"),
                _llm_model("first-chat"),
            ]
        )
    )
    _patch_conversation(mocker, last_used_model="gone-chat")
    _patch_inference_defaults(
        mocker, default_model="default-chat", default_provider="openai"
    )

    instance = registry.resolve_model_instance("llm", conversation_id="conv-1")

    assert isinstance(instance, TestModel)
    assert instance.model_name == "default-chat"


@pytest.mark.asyncio
async def test_resolve_model_instance_skips_unregistered_conversation_provider(
    mocker: Any,
) -> None:
    """Unregistered conversation last-used provider falls through to defaults."""
    registry = await _ready_registry(
        _openai_entry(
            allowed_models=[
                _llm_model("default-chat"),
                _llm_model("first-chat"),
            ]
        )
    )
    _patch_conversation(
        mocker, last_used_provider="missing", last_used_model="conv-chat"
    )
    _patch_inference_defaults(
        mocker, default_model="default-chat", default_provider="openai"
    )

    instance = registry.resolve_model_instance("llm", conversation_id="conv-1")

    assert isinstance(instance, TestModel)
    assert instance.model_name == "default-chat"


@pytest.mark.asyncio
async def test_resolve_model_instance_skips_unavailable_default_model(
    mocker: Any,
) -> None:
    """Unavailable conversation and default models fall through to first llm."""
    registry = await _ready_registry(
        _openai_entry(allowed_models=[_llm_model("first-chat")])
    )
    _patch_conversation(mocker, last_used_model="gone-chat")
    _patch_inference_defaults(
        mocker, default_model="gone-default", default_provider="openai"
    )

    instance = registry.resolve_model_instance("llm", conversation_id="conv-1")

    assert isinstance(instance, TestModel)
    assert instance.model_name == "first-chat"


@pytest.mark.asyncio
async def test_resolve_model_instance_skips_unregistered_default_provider(
    mocker: Any,
) -> None:
    """Unregistered configured default provider falls through to first llm."""
    registry = await _ready_registry(
        _openai_entry(allowed_models=[_llm_model("first-chat")])
    )
    _patch_conversation(mocker, last_used_model="gone-chat")
    _patch_inference_defaults(
        mocker, default_model="default-chat", default_provider="missing"
    )

    instance = registry.resolve_model_instance("llm", conversation_id="conv-1")

    assert isinstance(instance, TestModel)
    assert instance.model_name == "first-chat"


@pytest.mark.asyncio
async def test_resolve_model_instance_selects_first_available_llm_in_order(
    mocker: Any,
) -> None:
    """First-available llm uses registration order and skips non-llm providers."""
    registry = await _ready_registry(
        _openai_entry("embed-provider", allowed_models=_embed_only_models()),
        _openai_entry("rerank-provider", allowed_models=_rerank_only_models()),
        _openai_entry(
            "llm-provider",
            allowed_models=[
                _llm_model("first-chat"),
                _llm_model("second-chat"),
            ],
        ),
        _openai_entry(
            "later-provider",
            allowed_models=[_llm_model("later-chat")],
        ),
    )
    _patch_inference_defaults(mocker, default_model=None, default_provider=None)

    instance = registry.resolve_model_instance("llm")

    assert isinstance(instance, TestModel)
    assert instance.model_name == "first-chat"


@pytest.mark.asyncio
async def test_resolve_model_instance_raises_when_nothing_resolvable(
    mocker: Any,
) -> None:
    """Exhausted soft fallbacks raise NoModelConfiguredError."""
    registry = await _ready_registry(
        _openai_entry("embed-provider", allowed_models=_embed_only_models()),
        _openai_entry("rerank-provider", allowed_models=_rerank_only_models()),
    )
    _patch_conversation(
        mocker, last_used_provider="missing", last_used_model="gone-chat"
    )
    _patch_inference_defaults(
        mocker, default_model="gone-default", default_provider="missing"
    )

    with pytest.raises(NoModelConfiguredError) as exc_info:
        registry.resolve_model_instance("llm", conversation_id="conv-1")

    assert exc_info.value.model_type == "llm"

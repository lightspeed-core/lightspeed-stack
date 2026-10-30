"""Unit tests for the sentence-transformers inference provider."""

# pylint: disable=redefined-outer-name,protected-access

from typing import Any, Optional

import pytest
from sentence_transformers import CrossEncoder

from models.config import SentenceTransformersInferenceProviderEntry
from providers.inference.catalog import CatalogModel
from providers.inference.errors import (
    ModelNotAvailableError,
    ModelTypeNotSupportedError,
)
from providers.inference.registry import PROVIDER_CLASSES
from providers.inference.sentence_transformers.provider import (
    SentenceTransformersInferenceProvider,
)


def _entry(
    *,
    allowed_models: Optional[list[Any]] = None,
    device: Optional[str] = None,
    cache_dir: Optional[str] = None,
) -> SentenceTransformersInferenceProviderEntry:
    """Build a sentence-transformers provider configuration."""
    config: dict[str, Any] = {}
    if device is not None:
        config["device"] = device
    if cache_dir is not None:
        config["cache_dir"] = cache_dir
    return SentenceTransformersInferenceProviderEntry.model_validate(
        {
            "type": "sentence_transformers",
            "id": "sentence_transformers",
            "allowed_models": allowed_models
            or [
                {
                    "name": "embed",
                    "provider_model_id": "sentence-transformers/all-MiniLM-L6-v2",
                    "model_type": "embedding",
                },
                {
                    "name": "rerank",
                    "provider_model_id": "cross-encoder/ms-marco-MiniLM-L-6-v2",
                    "model_type": "rerank",
                },
            ],
            "config": config,
        }
    )


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
def provider() -> SentenceTransformersInferenceProvider:
    """Create a sentence-transformers provider with embed and rerank models."""
    return SentenceTransformersInferenceProvider(
        _entry(device="cpu", cache_dir="/tmp/hf-cache")
    )


def test_build_provider_returns_none(
    provider: SentenceTransformersInferenceProvider,
) -> None:
    """Inline provider has no PAI HTTP client or provider instance."""
    assert provider._build_provider() is None


@pytest.mark.asyncio
async def test_discover_models_returns_empty(
    provider: SentenceTransformersInferenceProvider,
) -> None:
    """Remote discovery is unsupported; catalog comes from allowed_models."""
    assert await provider._discover_models() == []


@pytest.mark.asyncio
async def test_load_catalog_from_allowed_models() -> None:
    """Allow-list only: infers types, prefers explicit model_type, omits llm."""
    provider = SentenceTransformersInferenceProvider(
        _entry(
            allowed_models=[
                "sentence-transformers/all-mpnet-base-v2",
                "cross-encoder/ms-marco-MiniLM-L-12-v2",
                {
                    "name": "forced-embed",
                    "provider_model_id": "cross-encoder/looks-like-rerank",
                    "model_type": "embedding",
                },
                {
                    "name": "chat",
                    "provider_model_id": "some-chat-model",
                    "model_type": "llm",
                },
            ]
        )
    )

    catalog = await provider._load_catalog()

    assert [
        (model.name, model.provider_model_id, model.model_type) for model in catalog
    ] == [
        (
            "sentence-transformers/all-mpnet-base-v2",
            "sentence-transformers/all-mpnet-base-v2",
            "embedding",
        ),
        (
            "cross-encoder/ms-marco-MiniLM-L-12-v2",
            "cross-encoder/ms-marco-MiniLM-L-12-v2",
            "rerank",
        ),
        (
            "forced-embed",
            "cross-encoder/looks-like-rerank",
            "embedding",
        ),
    ]


@pytest.mark.asyncio
async def test_initialize_does_not_load_models(mocker: Any) -> None:
    """Models stay lazy; initialize only builds the catalog."""
    sentence_transformer_cls = mocker.patch(
        "providers.inference.sentence_transformers.provider.SentenceTransformer",
    )
    cross_encoder_cls = mocker.patch(
        "providers.inference.sentence_transformers.provider.CrossEncoder",
    )
    provider = SentenceTransformersInferenceProvider(_entry())

    await provider.initialize()

    sentence_transformer_cls.assert_not_called()
    cross_encoder_cls.assert_not_called()
    assert provider._provider is None
    assert [
        (model.name, model.model_type) for model in provider.list_catalog_models()
    ] == [
        ("embed", "embedding"),
        ("rerank", "rerank"),
    ]


@pytest.mark.parametrize(
    ("device", "cache_dir"),
    [
        ("cpu", "/tmp/hf-cache"),
        (None, None),
    ],
)
def test_create_embedding_passes_config_and_caches(
    mocker: Any,
    device: Optional[str],
    cache_dir: Optional[str],
) -> None:
    """Builds SentenceTransformer with config, wraps in PAI, and caches."""
    provider = SentenceTransformersInferenceProvider(
        _entry(device=device, cache_dir=cache_dir)
    )
    runtime = mocker.Mock(name="sentence-transformer")
    wrapped = mocker.Mock(name="embedding-model")
    sentence_transformer_cls = mocker.patch(
        "providers.inference.sentence_transformers.provider.SentenceTransformer",
        return_value=runtime,
    )
    embedding_model_cls = mocker.patch(
        "providers.inference.sentence_transformers.provider."
        "SentenceTransformerEmbeddingModel",
        return_value=wrapped,
    )
    catalog = _catalog_model(
        name="embed",
        provider_model_id="sentence-transformers/all-MiniLM-L6-v2",
        model_type="embedding",
    )

    first = provider._create_embedding(catalog)
    second = provider._create_embedding(catalog)

    assert first is wrapped
    assert second is wrapped
    sentence_transformer_cls.assert_called_once_with(
        "sentence-transformers/all-MiniLM-L6-v2",
        device=device,
        cache_folder=cache_dir,
    )
    embedding_model_cls.assert_called_once_with(runtime)


@pytest.mark.parametrize(
    ("device", "cache_dir"),
    [
        ("cpu", "/tmp/hf-cache"),
        (None, None),
    ],
)
def test_create_rerank_passes_config_and_caches(
    mocker: Any,
    device: Optional[str],
    cache_dir: Optional[str],
) -> None:
    """Builds CrossEncoder with config and caches the instance."""
    provider = SentenceTransformersInferenceProvider(
        _entry(device=device, cache_dir=cache_dir)
    )
    created = mocker.Mock(name="cross-encoder", spec=CrossEncoder)
    cross_encoder_cls = mocker.patch(
        "providers.inference.sentence_transformers.provider.CrossEncoder",
        return_value=created,
    )
    catalog = _catalog_model(
        name="rerank",
        provider_model_id="cross-encoder/ms-marco-MiniLM-L-6-v2",
        model_type="rerank",
    )

    first = provider._create_rerank(catalog)
    second = provider._create_rerank(catalog)

    assert first is created
    assert second is created
    cross_encoder_cls.assert_called_once_with(
        "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device=device,
        cache_folder=cache_dir,
    )


def test_create_llm_is_unsupported(
    provider: SentenceTransformersInferenceProvider,
) -> None:
    """Rejects LLM construction because sentence-transformers never serves chat."""
    with pytest.raises(ModelTypeNotSupportedError) as exc_info:
        provider._create_llm(
            _catalog_model(
                name="chat",
                provider_model_id="should-not-load",
                model_type="llm",
            )
        )

    assert exc_info.value.model_type == "llm"
    assert exc_info.value.provider_id == "sentence_transformers"


@pytest.mark.asyncio
async def test_get_model_instance_resolves_embed_and_rerank(
    provider: SentenceTransformersInferenceProvider,
    mocker: Any,
) -> None:
    """Catalog names resolve to cached embedding and rerank instances."""
    await provider.initialize()
    embedding = mocker.Mock(name="embedding")
    reranker = mocker.Mock(name="rerank", spec=CrossEncoder)
    mocker.patch(
        "providers.inference.sentence_transformers.provider.SentenceTransformer",
    )
    mocker.patch(
        "providers.inference.sentence_transformers.provider."
        "SentenceTransformerEmbeddingModel",
        return_value=embedding,
    )
    mocker.patch(
        "providers.inference.sentence_transformers.provider.CrossEncoder",
        return_value=reranker,
    )

    assert provider.get_model_instance("embed", "embedding") is embedding
    assert provider.get_model_instance("rerank", "rerank") is reranker


@pytest.mark.asyncio
async def test_get_llm_raises_model_not_available(
    provider: SentenceTransformersInferenceProvider,
) -> None:
    """LLM requests fail with ModelNotAvailableError; llm is never catalogued."""
    await provider.initialize()

    with pytest.raises(ModelNotAvailableError) as exc_info:
        provider.get_model_instance("embed", "llm")

    assert exc_info.value.model_type == "llm"
    assert exc_info.value.provider_id == "sentence_transformers"
    assert exc_info.value.name == "embed"


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("sentence-transformers/all-MiniLM-L6-v2", "embedding"),
        ("sentence-transformers/all-mpnet-base-v2", "embedding"),
        ("nomic-ai/nomic-embed-text-v1.5", "embedding"),
        ("cross-encoder/ms-marco-MiniLM-L-6-v2", "rerank"),
        ("BAAI/bge-reranker-base", "rerank"),
        ("org/my_cross_encoder_model", "rerank"),
        ("antoinelouis/crossencoder-mMiniLMv2-L6-mmarcoFR", "rerank"),
        ("vendor/text-rerank-v1", "rerank"),
    ],
)
def test_infer_model_type(
    provider: SentenceTransformersInferenceProvider,
    model_id: str,
    expected: str,
) -> None:
    """Classifies Hub ids as embedding or rerank; never as llm."""
    assert provider._infer_model_type(model_id) == expected


def test_provider_registered_on_provider_classes() -> None:
    """Registry maps sentence_transformers to this provider class."""
    assert (
        PROVIDER_CLASSES["sentence_transformers"]
        is SentenceTransformersInferenceProvider
    )

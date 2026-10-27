"""Unit tests for the in-process sentence-transformers model cache."""

from typing import Any

from sentence_transformers import CrossEncoder

from providers.inference.sentence_transformers.model_cache import (
    SentenceTransformersModelCache,
)


def test_get_and_put_embedding_caches_by_provider_model_id(mocker: Any) -> None:
    """Stores embeddings by instance type and provider model id."""
    cache = SentenceTransformersModelCache()
    embed_a = mocker.Mock(name="embed-a")
    embed_b = mocker.Mock(name="embed-b")

    assert cache.get("model-a", "embedding") is None
    cache.put("model-a", embed_a)
    cache.put("model-b", embed_b)

    assert cache.get("model-a", "embedding") is embed_a
    assert cache.get("model-b", "embedding") is embed_b
    assert cache.get("model-a", "rerank") is None


def test_get_and_put_rerank_caches_by_provider_model_id(mocker: Any) -> None:
    """Stores cross-encoders by instance type and provider model id."""
    cache = SentenceTransformersModelCache()
    rerank_a = mocker.Mock(name="rerank-a", spec=CrossEncoder)
    rerank_b = mocker.Mock(name="rerank-b", spec=CrossEncoder)

    assert cache.get("model-a", "rerank") is None
    cache.put("model-a", rerank_a)
    cache.put("model-b", rerank_b)

    assert cache.get("model-a", "rerank") is rerank_a
    assert cache.get("model-b", "rerank") is rerank_b
    assert cache.get("model-a", "embedding") is None

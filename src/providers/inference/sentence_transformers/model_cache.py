"""In-process cache for sentence-transformers embedding and rerank models."""

from __future__ import annotations

from typing import Literal, Optional, overload

from pydantic_ai.embeddings import EmbeddingModel
from sentence_transformers import CrossEncoder


class SentenceTransformersModelCache:
    """Process-local cache of loaded embedding and rerank model instances."""

    def __init__(self) -> None:
        """Initialize empty embedding and rerank caches."""
        self._embeddings: dict[str, EmbeddingModel] = {}
        self._rerankers: dict[str, CrossEncoder] = {}

    @overload
    def get(
        self,
        provider_model_id: str,
        model_type: Literal["embedding"],
    ) -> Optional[EmbeddingModel]: ...

    @overload
    def get(
        self,
        provider_model_id: str,
        model_type: Literal["rerank"],
    ) -> Optional[CrossEncoder]: ...

    def get(
        self,
        provider_model_id: str,
        model_type: Literal["embedding", "rerank"],
    ) -> Optional[EmbeddingModel | CrossEncoder]:
        """Return a cached model when present.

        Args:
            provider_model_id: Cache key; the Hugging Face model id.
            model_type: Capability whose cache to read (embedding or rerank).

        Returns:
            The cached model, or None if it has not been stored.

        """
        match model_type:
            case "embedding":
                return self._embeddings.get(provider_model_id)
            case "rerank":
                return self._rerankers.get(provider_model_id)

    def put(
        self,
        provider_model_id: str,
        model: EmbeddingModel | CrossEncoder,
    ) -> None:
        """Store a model in the cache.

        The target store is chosen from the instance type: CrossEncoder goes
        to the rerank cache, anything else to the embedding cache.

        Args:
            provider_model_id: Cache key; the Hugging Face model id.
            model: Model instance to cache.

        """
        if isinstance(model, CrossEncoder):
            self._rerankers[provider_model_id] = model
        else:
            self._embeddings[provider_model_id] = model

"""Local sentence-transformers inference provider (embedding and rerank)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from pydantic_ai.embeddings.sentence_transformers import (
    SentenceTransformerEmbeddingModel,
)
from pydantic_ai.providers import Provider
from sentence_transformers import CrossEncoder, SentenceTransformer

from configuration import configuration
from log import get_logger
from models.config import SentenceTransformersInferenceProviderEntry
from providers.inference.base import InferenceProvider
from providers.inference.catalog import CatalogModel, DiscoveredModel
from providers.inference.sentence_transformers.model_cache import (
    SentenceTransformersModelCache,
)

if TYPE_CHECKING:
    from pydantic_ai.embeddings import EmbeddingModel

    from providers.inference.types import ModelType

logger = get_logger(__name__)


class SentenceTransformersInferenceProvider(
    InferenceProvider[SentenceTransformersInferenceProviderEntry, Provider[Any]]
):
    """Inference provider for local sentence-transformers embedding and rerank.

    This provider has no HTTP client and no remote discovery. The configured
    allowed_models list is the catalog. Chat models are never exposed.
    """

    def __init__(self, entry: SentenceTransformersInferenceProviderEntry) -> None:
        """Initialize with an empty in-process model cache.

        Args:
            entry: Provider configuration entry with a non-empty allow-list.

        """
        super().__init__(entry)
        self._cache = SentenceTransformersModelCache()

    def _build_provider(self) -> Optional[Provider[Any]]:
        """Return no Pydantic AI provider; models run in-process.

        Returns:
            Always None.

        """
        return None

    async def _discover_models(self) -> list[DiscoveredModel]:
        """Remote discovery is unsupported for sentence-transformers.

        Returns:
            An empty list. Catalog construction uses allowed_models only.

        """
        return []

    async def _load_catalog(self) -> list[CatalogModel]:
        """Build the catalog from allowed_models plus configured rerank references.

        Equivalent to the base-class skip_model_discovery path. Entries typed
        as llm are omitted so this provider never exposes chat models.

        Also adds a rerank row when its provider id matches this provider id.

        Returns:
            Catalog rows for embedding and rerank models only.

        """
        catalog: list[CatalogModel] = []
        for allowed in self._entry.allowed_models:
            model_type = allowed.model_type or self._infer_model_type(
                allowed.provider_model_id
            )
            if model_type == "llm":
                logger.warning(
                    "Omitting configured model %r with provider model ID %r "
                    "from sentence-transformers provider %r; llm is unsupported",
                    allowed.name,
                    allowed.provider_model_id,
                    self.provider_id,
                )
                continue
            catalog.append(
                CatalogModel(
                    name=allowed.name,
                    provider_model_id=allowed.provider_model_id,
                    model_type=model_type,
                    metadata=dict(allowed.metadata),
                )
            )

        rerank_catalog_names = {
            model.name for model in catalog if model.model_type == "rerank"
        }
        if row := self._inline_reranker_catalog_row(rerank_catalog_names):
            catalog.append(row)
        return catalog

    def _inline_reranker_catalog_row(
        self,
        rerank_catalog_names: set[str],
    ) -> Optional[CatalogModel]:
        """Return inline reranker as a catalog row when missing from the allow-list.

        Args:
            rerank_catalog_names: Catalog names already used by rerank entries.

        Returns:
            A rerank catalog row for this provider, or None if not applicable.

        """
        reranker = configuration.reranker
        if (
            reranker is None
            or not reranker.model
            or reranker.provider != self.provider_id
            or reranker.model in rerank_catalog_names
        ):
            return None

        model_name = reranker.model
        logger.debug(
            "Registered RAG-configured rerank model %r on "
            "sentence-transformers provider %r",
            model_name,
            self.provider_id,
        )
        return CatalogModel(
            name=model_name,
            provider_model_id=model_name,
            model_type="rerank",
        )

    def _create_embedding(self, model: CatalogModel) -> EmbeddingModel:
        """Create or reuse a cached Pydantic AI sentence-transformers embedding model.

        Args:
            model: Catalog entry describing the embedding model to instantiate.

        Returns:
            A cached Pydantic AI embedding model for the provider model id.

        """
        provider_model_id = model.provider_model_id
        cached = self._cache.get(provider_model_id, "embedding")
        if cached is not None:
            return cached

        config = self._entry.config
        embedding = SentenceTransformerEmbeddingModel(
            SentenceTransformer(
                provider_model_id,
                device=config.device,
                cache_folder=config.cache_dir,
            )
        )
        self._cache.put(provider_model_id, embedding)
        return embedding

    def _create_rerank(self, model: CatalogModel) -> CrossEncoder:
        """Create or reuse a cached sentence-transformers cross-encoder.

        Args:
            model: Catalog entry describing the reranker to instantiate.

        Returns:
            A cached CrossEncoder for the provider model id.

        """
        provider_model_id = model.provider_model_id
        cached = self._cache.get(provider_model_id, "rerank")
        if cached is not None:
            return cached

        config = self._entry.config
        reranker = CrossEncoder(
            provider_model_id,
            device=config.device,
            cache_folder=config.cache_dir,
        )
        self._cache.put(provider_model_id, reranker)
        return reranker

    def _infer_model_type(
        self,
        provider_model_id: str,
        **kwargs: Any,
    ) -> ModelType:
        """Infer embedding vs rerank when allowed_models model_type is omitted.

        Args:
            provider_model_id: Hugging Face model id or local path.
            **kwargs: Unused; accepted for base-class compatibility.

        Returns:
            rerank when the id looks like a cross-encoder or reranker,
            otherwise embedding. Never llm.

        """
        _ = kwargs
        normalized = provider_model_id.lower().replace("-", "").replace("_", "")
        if "crossencoder" in normalized or "rerank" in normalized:
            return "rerank"
        return "embedding"

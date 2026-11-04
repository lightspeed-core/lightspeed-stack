"""Local sentence-transformers inference provider (embedding and rerank)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from pydantic_ai.embeddings.sentence_transformers import (
    SentenceTransformerEmbeddingModel,
)
from pydantic_ai.providers import Provider
from sentence_transformers import CrossEncoder, SentenceTransformer

from configuration import LogicError, configuration
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
        """Build the catalog from allowed models plus configured defaults.

        Equivalent to the base-class skip_model_discovery path. Entries typed
        as llm are omitted so this provider never exposes chat models.

        For backward compatibility, also registers models referenced by the
        loaded application configuration when those local names are absent
        (name == provider_model_id): the inline reranker model when it targets
        this provider, and embedding models from BYOK stores / vector-store
        providers.

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
        return self._with_configured_catalog_models(catalog)

    def _with_configured_catalog_models(
        self,
        catalog: list[CatalogModel],
    ) -> list[CatalogModel]:
        """Append config-referenced embedding/rerank models when missing.

        Args:
            catalog: Catalog built from configured allowed models.

        Returns:
            Catalog with application-config model IDs added under matching
            local names when those names are absent. No-op when application
            configuration is not loaded.

        """
        try:
            root = configuration.configuration
        except LogicError:
            return catalog

        existing_names = {model.name for model in catalog}
        defaults: list[tuple[str, ModelType]] = []

        reranker = root.rag.retrieval.inline.reranker
        if (
            reranker is not None
            and reranker.provider == self.provider_id
            and reranker.model
        ):
            defaults.append((reranker.model, "rerank"))

        # There is no dedicated default-embedding config; register embedding
        # models declared on BYOK stores and dynamic vector-store providers.
        for store in root.rag.byok.stores:
            if store.embedding_model:
                defaults.append((store.embedding_model, "embedding"))
        for vs_provider in root.vector_store.providers:
            if vs_provider.embedding_model:
                defaults.append((vs_provider.embedding_model, "embedding"))

        for model_id, model_type in defaults:
            if model_id in existing_names:
                continue
            catalog.append(
                CatalogModel(
                    name=model_id,
                    provider_model_id=model_id,
                    model_type=model_type,
                )
            )
            existing_names.add(model_id)
            logger.debug(
                "Registered configured %s model %r on sentence-transformers "
                "provider %r for backward compatibility",
                model_type,
                model_id,
                self.provider_id,
            )
        return catalog

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

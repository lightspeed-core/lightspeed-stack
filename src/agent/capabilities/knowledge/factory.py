"""Factory for building knowledge capabilities from knowledge source settings."""

from typing import Literal, Optional

from pydantic_ai.embeddings import Embedder
from pydantic_ai.embeddings.sentence_transformers import (
    SentenceTransformerEmbeddingModel,
)

import constants
from agent.types.settings import KnowledgeSourceSettings
from configuration import configuration
from knowledge.capability import Knowledge
from knowledge.sources.base import KnowledgeSource
from knowledge.sources.faiss import FaissKnowledgeSource
from log import get_logger

logger = get_logger(__name__)


class KnowledgeFactory:
    """Factory for building knowledge capabilities."""

    @staticmethod
    def build_source(setting: KnowledgeSourceSettings) -> Optional[KnowledgeSource]:
        """Build one knowledge source from settings and the loaded RAG configuration.

        The source named by ``setting.id`` is resolved against
        ``configuration.rag``. Disabled settings and unknown ids produce no
        source. OKP and backends other than Faiss are not implemented.

        Parameters:
            setting: Knowledge source settings.

        Returns:
            A knowledge source, or ``None`` when the setting is disabled or
            no matching RAG store is configured.

        Raises:
            NotImplementedError: If the matching source uses a backend that
                is not implemented.
            ValueError: If a Faiss store is missing ``db_path``.

        """
        if not setting.enabled:
            return None

        if setting.id == constants.OKP_RAG_ID:
            raise NotImplementedError("OKP knowledge source is not implemented")

        rag = configuration.rag
        store = next(
            (
                candidate
                for candidate in rag.byok.stores
                if candidate.rag_id == setting.id
            ),
            None,
        )
        if store is None:
            logger.warning(
                "Knowledge source '%s' is not configured; skipping",
                setting.id,
            )
            return None

        mode: set[Literal["tool", "auto"]] = set()
        limits: list[int] = []
        if setting.id in rag.retrieval.inline.sources:
            mode.add("auto")
            limits.append(rag.retrieval.inline.max_chunks)
        if setting.id in rag.retrieval.tool.sources:
            mode.add("tool")
            limits.append(rag.retrieval.tool.max_chunks)

        match store.backend:
            case "faiss":
                if store.db_path is None:
                    raise ValueError(
                        f"Knowledge source '{store.rag_id}' uses the faiss backend "
                        "but has no db_path"
                    )
                return FaissKnowledgeSource(
                    name=store.rag_id,
                    db_path=store.db_path,
                    vector_store_id=store.vector_db_id,
                    embedder=Embedder(
                        SentenceTransformerEmbeddingModel(store.embedding_model)
                    ),
                    top_k=max(limits) if limits else rag.byok.max_chunks,
                    score_threshold=store.relevance_cutoff_score,
                    mode=mode or {"tool"},
                )
            case _:
                raise NotImplementedError(
                    f"Knowledge source backend '{store.backend}' is not implemented"
                )

    @staticmethod
    def build_capabilities(
        settings: list[KnowledgeSourceSettings],
    ) -> Optional[Knowledge]:
        """Build a knowledge capability from knowledge source settings.

        Parameters:
            settings: Knowledge source settings to turn into a capability.

        Returns:
            One knowledge capability covering every enabled, configured
            source, or ``None`` when no sources are built.

        Raises:
            NotImplementedError: If a matching source uses a backend that is
                not implemented.

        """
        sources = [
            source
            for setting in settings
            if (source := KnowledgeFactory.build_source(setting)) is not None
        ]
        if not sources:
            return None

        return Knowledge(sources=sources)

"""Singleton registry of configured knowledge sources."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Final, Optional

from knowledge.errors import (
    DuplicateKnowledgeSourceError,
    KnowledgeSourceNotFoundError,
)
from knowledge.sources.faiss import FaissKnowledgeSource
from knowledge.sources.okp import OkpKnowledgeSource
from knowledge.sources.pgvector import PgVectorKnowledgeSource
from log import get_logger
from utils.types import Singleton

if TYPE_CHECKING:
    from knowledge.sources.base import KnowledgeSource
    from models.config import RagConfiguration

KNOWLEDGE_SOURCE_CLASSES: Final[
    dict[str, type[FaissKnowledgeSource | PgVectorKnowledgeSource]]
] = {
    "faiss": FaissKnowledgeSource,
    "pgvector": PgVectorKnowledgeSource,
}

logger = get_logger(__name__)


class KnowledgeSourceRegistry(metaclass=Singleton):
    """Registry of configured knowledge sources."""

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._sources: dict[str, KnowledgeSource] = {}

    async def initialize(self, rag: RagConfiguration) -> None:
        """Register knowledge sources described by a RAG configuration.

        BYOK stores are built in configuration order. OKP is appended when
        retrieval includes it. Sources stay in memory for the process lifetime.
        A duplicate name leaves the registry unchanged.

        Args:
            rag: RAG configuration to load at startup.

        Raises:
            DuplicateKnowledgeSourceError: A source name is repeated in
                ``rag`` or is already registered.

        """
        sources: dict[str, KnowledgeSource] = dict(self._sources)
        for source in _configured_sources(rag):
            if source.name in sources:
                raise DuplicateKnowledgeSourceError(source.name)
            sources[source.name] = source
        self._sources = sources

        source_names = [source.name for source in self.list_sources()]
        logger.info(
            "Knowledge source registry initialized with %d source(s): %s",
            len(source_names),
            source_names,
        )

    def find_source(self, name: str) -> Optional[KnowledgeSource]:
        """Find a knowledge source by name when absence is acceptable.

        Args:
            name: Knowledge source name from configuration.

        Returns:
            The configured source, or None if it is not registered.

        """
        return self._sources.get(name)

    def get_source(self, name: str) -> KnowledgeSource:
        """Get a knowledge source by name when absence is an error.

        Args:
            name: Knowledge source name from configuration.

        Returns:
            The configured source.

        Raises:
            KnowledgeSourceNotFoundError: If the source is not registered.

        """
        if (source := self.find_source(name)) is None:
            raise KnowledgeSourceNotFoundError(name)
        return source

    def list_sources(self) -> list[KnowledgeSource]:
        """List configured knowledge sources in registration order."""
        return list(self._sources.values())


def _configured_sources(rag: RagConfiguration) -> Iterator[KnowledgeSource]:
    """Yield knowledge sources described by ``rag``, in registration order.

    Args:
        rag: RAG configuration to read.

    Yields:
        One source per BYOK store, then the OKP source when retrieval
        includes it.

    """
    for store in rag.byok.stores:
        source_cls = KNOWLEDGE_SOURCE_CLASSES[store.backend]
        yield source_cls.from_rag_configuration(rag, store)
    if okp := OkpKnowledgeSource.from_rag_configuration(rag):
        yield okp

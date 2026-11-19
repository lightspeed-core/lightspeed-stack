"""Abstract base for pluggable knowledge sources."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic_ai.embeddings import Embedder, EmbeddingSettings

from knowledge.types import KnowledgeMatch, KnowledgeReadiness


@dataclass
class KnowledgeSource(ABC):
    """Knowledge source to search, with its own exposure mode.

    `mode` lives here (rather than on whatever capability attaches this
    source) so each source controls how *it* is exposed, independent of how
    many other sources a `Knowledge` capability combines it with.
    """

    name: str
    """Name of the knowledge source."""

    mode: set[Literal["tool", "auto"]] = field(
        default_factory=lambda: {"tool"}, kw_only=True
    )
    """
    `'tool'`: exposes a model-callable `search_<name>` tool for this source.
    `'auto'`: searches the latest user prompt automatically and injects this
    source's matches as bounded, delimited context on every model request.
    """

    score_multiplier: float = field(default=1.0, kw_only=True)
    """Weight applied to this source's scores after merged matches are ranked.

    ``search`` returns the raw score, and the cutoff uses that raw score.
    Values above 1 boost this source against the others; values below 1
    reduce it. OKP stays at 1 because its scores are not on the BYOK scale.
    """

    @abstractmethod
    async def search(self, prompt: str) -> list[KnowledgeMatch]:
        """Search the knowledge source for matches."""

    @abstractmethod
    async def readiness(self) -> KnowledgeReadiness:
        """Check the readiness of the knowledge source."""


class VectorStore(ABC):  # pylint: disable=too-few-public-methods
    """Vector store to search by embedding vector."""

    @abstractmethod
    async def search(
        self,
        embeddings: list[list[float]],
        limit: int = 5,
        threshold: float = 0.0,
    ) -> list[KnowledgeMatch]:
        """Search the vector store for matches.

        Args:
            embeddings: Query embedding vectors.
            limit: The maximum number of matches to return.
            threshold: The minimum similarity score to return.

        """


@dataclass
class VectorStoreKnowledgeSource(KnowledgeSource):
    """Knowledge source that embeds queries and searches a :class:`VectorStore`."""

    store: VectorStore
    """Vector store to search."""

    embedder: Embedder
    """Embedder to use for the search."""

    embedding_settings: Optional[EmbeddingSettings] = None
    """Settings to use for the embedding."""

    max_matches: int = 5
    """Maximum number of matches to return."""

    score_threshold: float = 0.0
    """Minimum similarity score to return."""

    async def search(self, prompt: str) -> list[KnowledgeMatch]:
        """Search the vector store for matches.

        Hits below `score_threshold` are dropped using the raw score.
        `score_multiplier` is not applied here.
        """
        embedding_result = await self.embedder.embed_query(
            prompt, settings=self.embedding_settings
        )
        embeddings = [list(vector) for vector in embedding_result.embeddings]
        return await self.store.search(
            embeddings,
            limit=self.max_matches,
            threshold=self.score_threshold,
        )

    @abstractmethod
    async def readiness(self) -> KnowledgeReadiness:
        """Check the readiness of the vector store."""

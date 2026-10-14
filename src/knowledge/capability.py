"""``Knowledge`` capability: vector-similarity search ("RAG") over one or more pluggable ``KnowledgeSource``s.

Each attached :class:`~lightspeed.core.agent.knowledge.sources.base.KnowledgeSource`
declares its own `mode` -- exposed to the agent via a single model-callable
`search_knowledge` tool spanning every tool-mode source (`'tool'`), as
automatic inline context injection of the merged, ranked matches (`'auto'`), or both -- so a
single `Knowledge` capability can combine several sources, each exposed
however it needs to be. Configure sources under `knowledge.sources` in
`lightspeed-stack.yaml` (see
:class:`~lightspeed.core.agent.knowledge.factory.KnowledgeCapabilityFactory`),
or construct this directly for programmatic use, the same way
:class:`pydantic_ai_harness.memory.Memory` is used standalone.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Optional

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.tools import AgentDepsT
from sentence_transformers import CrossEncoder

from knowledge.reranker import rerank
from knowledge.sources.base import KnowledgeSource
from knowledge.types import KnowledgeMatch


async def search_sources(
    sources: Sequence[KnowledgeSource],
    prompt: str,
    reranker: Optional[CrossEncoder] = None,
) -> list[KnowledgeMatch]:
    """Search `sources` concurrently and return merged matches, ranked highest-score-first.

    Each match is tagged with `metadata['knowledge_source']` so hits stay
    attributable after the merge. Ranked by cross-encoder score if
    `reranker` is set, otherwise by each source's own similarity score.
    """
    results = await asyncio.gather(*(source.search(prompt) for source in sources))
    matches = [
        replace(match, metadata={**match.metadata, "knowledge_source": source.name})
        for source, source_matches in zip(sources, results)
        for match in source_matches
    ]
    if reranker:
        return await rerank(prompt, matches, reranker)
    return sorted(matches, key=lambda match: match.score, reverse=True)


@dataclass
class Knowledge(AbstractCapability[AgentDepsT]):
    """Vector-similarity search ("RAG") over one or more :class:`KnowledgeSource` instances."""

    sources: Sequence[KnowledgeSource]
    """Knowledge sources to search. Each source's own `mode` controls how it's exposed."""

    reranker: Optional[CrossEncoder] = None
    """Optional `sentence-transformers` cross-encoder model id (e.g.
    `'cross-encoder/ms-marco-MiniLM-L-6-v2'`) used to rerank matches by
    relevance to the query before they're returned or injected. Loaded
    lazily on first use; requires the `sentence-transformers` package."""

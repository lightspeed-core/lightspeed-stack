"""``Knowledge`` capability: vector-similarity search ("RAG") over knowledge sources.

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

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.tools import AgentDepsT
from sentence_transformers import CrossEncoder

if TYPE_CHECKING:
    from knowledge.sources.base import KnowledgeSource


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

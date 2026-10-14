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
from pydantic_ai.messages import TextContent, UserContent
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.tools import AgentDepsT, RunContext
from pydantic_ai.toolsets import AgentToolset
from sentence_transformers import CrossEncoder

from knowledge.reranker import rerank
from knowledge.sources.base import KnowledgeSource
from knowledge.toolset import KnowledgeToolset
from knowledge.types import KnowledgeMatch
from knowledge.utils import append_latest_message, extract_latest_message_text


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

    async def before_model_request(
        self,
        ctx: RunContext[AgentDepsT],
        request_context: ModelRequestContext,
    ) -> ModelRequestContext:
        """Search every auto-mode source concurrently, rank the merged matches, and inject them."""

        def to_message(matches: list[KnowledgeMatch]) -> Optional[UserContent]:
            if not matches:
                return None

            match_blocks = [
                f'<match id="{match.id}" source="{match.source}" '
                f'knowledge_source="{match.metadata.get("knowledge_source", "")}">\n'
                f"{match.content.strip()}\n"
                f"</match>"
                for match in matches
            ]

            body = "\n\n".join(match_blocks)

            return TextContent(
                content=f"<knowledge>\n{body}\n</knowledge>",
                metadata={
                    "kind": "knowledge",
                    "knowledge_scores": {match.id: match.score for match in matches},
                    "knowledge_metadata": {
                        match.id: match.metadata for match in matches
                    },
                    "knowledge_sources": {
                        match.id: match.metadata.get("knowledge_source")
                        for match in matches
                    },
                },
            )

        auto_sources = [source for source in self.sources if "auto" in source.mode]
        if not auto_sources:
            return request_context

        prompt = extract_latest_message_text(request_context.messages)
        if not prompt:
            return request_context

        matches = await search_sources(auto_sources, prompt, self.reranker)
        if message := to_message(matches):
            append_latest_message(request_context.messages, message)

        return request_context

    def get_toolset(self) -> AgentToolset[AgentDepsT] | None:
        """Provide a single `search_knowledge` tool spanning every source whose `mode` includes `'tool'`."""
        tool_sources = [source for source in self.sources if "tool" in source.mode]
        return KnowledgeToolset(tool_sources, reranker=self.reranker) if tool_sources else None

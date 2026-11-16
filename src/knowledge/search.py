"""Concurrent multi-source knowledge search with optional cross-encoder reranking."""

import asyncio
from dataclasses import replace
from typing import Optional

from sentence_transformers import CrossEncoder

from knowledge.reranker import rerank
from knowledge.sources.base import KnowledgeSource
from knowledge.types import KnowledgeMatch


def _apply_score_multipliers(
    ranked: list[KnowledgeMatch],
    sources: list[KnowledgeSource],
) -> list[KnowledgeMatch]:
    """Scale each ranked match by the multiplier of the source that found it.

    A source whose multiplier is 1 leaves its matches unchanged. When every
    source is 1, `ranked` itself is returned.

    Args:
        ranked: Matches already ordered by rerank or raw similarity score.
            Each match's ``metadata['knowledge_source']`` is the source name.
        sources: Sources that produced `ranked`.

    Returns:
        `ranked` with each score multiplied by that source's
        `score_multiplier`. Order is unchanged.

    """
    multipliers = {source.name: source.score_multiplier for source in sources}
    if all(multiplier == 1.0 for multiplier in multipliers.values()):
        return ranked
    return [
        (
            match
            if multipliers[str(match.metadata["knowledge_source"])] == 1.0
            else replace(
                match,
                score=match.score
                * multipliers[str(match.metadata["knowledge_source"])],
            )
        )
        for match in ranked
    ]


async def search_sources(
    sources: list[KnowledgeSource],
    prompt: str,
    reranker: Optional[CrossEncoder] = None,
    *,
    limit: Optional[int] = None,
) -> list[KnowledgeMatch]:
    """Search `sources` concurrently, rank the merge, then scale each score.

    Each match is tagged with `metadata['knowledge_source']` so hits stay
    attributable after the merge. Ranking uses the raw scores from
    `source.search`: the cross-encoder score when `reranker` is set,
    otherwise the similarity score. After that ordering, each score is
    multiplied by the source's `score_multiplier`. `limit` keeps the first
    matches in that ranked order.

    Args:
        sources: Knowledge sources to search together.
        prompt: Natural-language query forwarded to every source.
        reranker: Optional cross-encoder used to rerank the merged matches.
        limit: Maximum matches to return after ranking. ``None`` keeps all.

    Returns:
        Merged matches in ranked order, with scores scaled by each source's
        `score_multiplier`, truncated to `limit` when set.

    """
    results = await asyncio.gather(*(source.search(prompt) for source in sources))
    matches = [
        replace(
            match,
            metadata={**match.metadata, "knowledge_source": source.name},
        )
        for source, source_matches in zip(sources, results)
        for match in source_matches
    ]
    if reranker:
        ranked = await rerank(prompt, matches, reranker)
    else:
        ranked = sorted(matches, key=lambda match: match.score, reverse=True)
    weighted = _apply_score_multipliers(ranked, sources)
    if limit is None:
        return weighted
    return weighted[:limit]

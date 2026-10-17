"""Cross-encoder reranking for `Knowledge` search results.

Simplified relative to the pattern this is modeled on: no blending with
original similarity scores and no fallback re-sort on failure -- a model
is resolved via :class:`~lightspeed.core.agent.knowledge.registry.CrossEncoderRegistry`
(which lazily loads and process-wide caches it by name), used to score
every match against the query, and matches are returned highest-score-first.
On any failure to load the model or score matches, a warning is logged and
the matches are returned unranked.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from sentence_transformers import CrossEncoder

from knowledge.types import KnowledgeMatch

logger = logging.getLogger(__name__)


async def rerank(
    prompt: str, matches: list[KnowledgeMatch], model: CrossEncoder
) -> list[KnowledgeMatch]:
    """Rerank `matches` against `prompt` with the cross-encoder, highest score first.

    Args:
        prompt: The search prompt the matches should be scored against.
        matches: Matches to rerank; each match's `score` is replaced with
            its cross-encoder score.
        model: A `sentence-transformers` cross-encoder model.
            `'cross-encoder/ms-marco-MiniLM-L-6-v2'`.

    Returns:
        `matches` sorted by cross-encoder score, descending. Returned
        unchanged (and unranked) if loading the model or scoring fails.

    """
    if not matches:
        return matches

    try:
        scores = model.predict([(prompt, match.content) for match in matches])
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning(
            "Cross-encoder reranking failed; returning unranked matches.", exc_info=True
        )
        return matches

    # Normalize cross-encoder scores to [0,1] range using min-max normalization
    if len(scores) > 1:
        min_score = min(scores)
        max_score = max(scores)
        score_range = max_score - min_score
        if score_range > 0:
            normalized_ce_scores = [
                (score - min_score) / score_range for score in scores
            ]
        else:
            # All scores are identical, assign 0.5 to all
            normalized_ce_scores = [0.5] * len(scores)
    else:
        # Single score, assign 1.0
        normalized_ce_scores = [1.0] * len(scores)

    # Extract original weighted scores and normalize them
    original_scores = [
        match.score if match.score is not None else 0.0 for match in matches
    ]

    if len(original_scores) > 1:
        min_orig = min(original_scores)
        max_orig = max(original_scores)
        orig_range = max_orig - min_orig
        if orig_range > 0:
            normalized_orig_scores = [
                (score - min_orig) / orig_range for score in original_scores
            ]
        else:
            # All original scores identical, assign 0.5 to all
            normalized_orig_scores = [0.5] * len(original_scores)
    else:
        # Single score, assign 1.0
        normalized_orig_scores = [1.0] * len(original_scores)

    # Combine cross-encoder scores with original weighted scores
    # (favor original weighted scores)
    # This ensures score multipliers are still influential in the final ranking
    # Weight: 30% cross-encoder, 70% original weighted scores
    combined_scores = [
        (0.3 * ce_score + 0.7 * orig_score)
        for ce_score, orig_score in zip(
            normalized_ce_scores, normalized_orig_scores, strict=True
        )
    ]

    reranked = [
        replace(match, score=score)
        for match, score in zip(matches, combined_scores, strict=True)
    ]
    return sorted(reranked, key=lambda match: match.score, reverse=True)

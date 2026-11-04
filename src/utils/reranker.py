"""Reranker utilities for RAG chunk reranking.

This module contains functionality for reranking RAG chunks using cross-encoder models
to improve the relevance of retrieved documents in RAG applications.
"""

import asyncio
from typing import Optional

from sentence_transformers import CrossEncoder

import constants
from configuration import configuration
from log import get_logger
from models.common.turn_summary import RAGChunk
from providers.inference.errors import (
    ModelNotAvailableError,
    ModelTypeNotSupportedError,
    ProviderNotFoundError,
)
from providers.inference.registry import ProviderRegistry

logger = get_logger(__name__)


async def _get_cross_encoder() -> Optional[CrossEncoder]:
    """Resolve the cross-encoder from the inference provider registry.

    Uses ``configuration.reranker.provider`` and ``configuration.reranker.model``
    (catalog name on that provider) with the typed rerank getter.

    Returns:
        Loaded CrossEncoder model instance, or None if resolution fails
        or reranking is disabled.

    """
    if (
        not configuration.reranker or not configuration.reranker.enabled
    ):  # pylint: disable=no-member
        logger.debug("Reranker is disabled, not loading cross-encoder model")
        return None

    provider_id = configuration.reranker.provider
    model_id = configuration.reranker.model

    try:
        # Model construction may load Hub weights; keep it off the event loop.
        model = await asyncio.to_thread(
            ProviderRegistry().resolve_model_instance,
            "rerank",
            provider_id,
            model_id,
        )
        logger.info(
            "Resolved cross-encoder for RAG reranking: provider=%s model=%s",
            provider_id,
            model_id,
        )
        return model
    except (
        ProviderNotFoundError,
        ModelNotAvailableError,
        ModelTypeNotSupportedError,
    ) as e:
        logger.warning(
            "Could not resolve cross-encoder for reranking "
            "(provider=%s model=%s): %s",
            provider_id,
            model_id,
            e,
        )
        return None


# pylint: disable=too-many-locals,too-many-branches
async def rerank_chunks_with_cross_encoder(
    query: str,
    chunks: list[RAGChunk],
    top_k: int,
) -> list[RAGChunk]:
    """Rerank chunks using configurable cross-encoder model.

    Args:
        query: The search query
        chunks: RAG chunks to rerank (should contain original weighted scores)
        top_k: Number of top chunks to return

    Returns:
        Top top_k chunks sorted by combined cross-encoder and weighted score (descending)

    """
    if not chunks:
        return []

    try:
        model = await _get_cross_encoder()
        if model is None:
            raise RuntimeError("Failed to resolve cross-encoder model from registry")

        logger.debug("Using registry-resolved cross-encoder for RAG reranking")

        # Create query-chunk pairs for scoring
        pairs = [(query, chunk.content) for chunk in chunks]
        scores = await asyncio.to_thread(model.predict, pairs)

        if hasattr(scores, "tolist"):
            scores = scores.tolist()

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
            chunk.score if chunk.score is not None else 0.0 for chunk in chunks
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

        # Combine scores with chunks and sort by combined score (descending)
        indexed = list(zip(combined_scores, chunks, strict=True))
        indexed.sort(key=lambda x: x[0], reverse=True)
        top_indexed = indexed[:top_k]

        # Log the score combination results
        logger.info(
            "Cross-encoder scoring completed: combined %d cross-encoder + "
            "original scores (30%%/70%% mix), returning top %d chunks",
            len(chunks),
            len(top_indexed),
        )
        if logger.isEnabledFor(10):  # DEBUG level
            for i, (score, chunk) in enumerate(top_indexed[:3]):  # Show top 3
                logger.debug(
                    "Reranked chunk %d: source=%s, combined_score=%.3f, content_preview='%.50s...'",
                    i + 1,
                    chunk.source,
                    score,
                    chunk.content,
                )

        # Return RAGChunk list with combined scores
        return [
            chunk.model_copy(update={"score": float(score)})
            for score, chunk in top_indexed
        ]

    except Exception as e:  # pylint: disable=broad-exception-caught  # noqa: BLE001
        logger.warning(
            "Cross-encoder reranking failed, falling back to original scoring: %s", e
        )
        # Fallback: sort by original score and take top_k
        sorted_chunks = sorted(
            chunks,
            key=lambda c: c.score if c.score is not None else float("-inf"),
            reverse=True,
        )
        return sorted_chunks[:top_k]


def apply_byok_rerank_boost(
    chunks: list[RAGChunk], boost: float = constants.BYOK_RAG_RERANK_BOOST
) -> list[RAGChunk]:
    """Apply a score multiplier to BYOK chunks (source != OKP) and re-sort by score.

    Args:
        chunks: RAG chunks after reranking (may be from BYOK or Solr).
        boost: Multiplier applied to BYOK chunk scores. Solr chunks unchanged.

    Returns:
        Same chunks with BYOK scores boosted, sorted by score descending.

    """
    boosted = []
    for chunk in chunks:
        score = chunk.score if chunk.score is not None else float("-inf")
        if chunk.source != constants.OKP_RAG_ID:
            score = score * boost
        boosted.append(chunk.model_copy(update={"score": score}))
    boosted.sort(
        key=lambda c: c.score if c.score is not None else float("-inf"),
        reverse=True,
    )

    return boosted

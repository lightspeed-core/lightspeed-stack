"""Helpers for inferring catalog model types from known model ids."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, TypeAliasType, get_args

from pydantic_ai.embeddings import KnownEmbeddingModelName
from pydantic_ai.models import KnownModelName

if TYPE_CHECKING:
    from providers.inference.types import ModelType


def _model_ids_from_known_names(known_names: TypeAliasType) -> frozenset[str]:
    """Extract unprefixed model ids from a Pydantic AI known-name type alias.

    Args:
        known_names: A Pydantic AI known-name type alias.

    Returns:
        The set of model ids with provider prefixes removed.

    """
    return frozenset(name.split(":", 1)[-1] for name in get_args(known_names.__value__))


KNOWN_LLM_IDS: frozenset[str] = _model_ids_from_known_names(KnownModelName)
KNOWN_EMBEDDING_IDS: frozenset[str] = _model_ids_from_known_names(
    KnownEmbeddingModelName
)


def infer_model_type_from_pai_known_names(
    provider_model_id: str,
) -> Optional[ModelType]:
    """Infer model type from Pydantic AI's known model names.

    Args:
        provider_model_id: Model id as reported by the inference provider.

    Returns:
        The inferred model type, or None if the model id is unknown.

    """
    if provider_model_id in KNOWN_EMBEDDING_IDS:
        return "embedding"
    if provider_model_id in KNOWN_LLM_IDS:
        return "llm"
    return None

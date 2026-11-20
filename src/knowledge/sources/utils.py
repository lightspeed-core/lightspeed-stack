"""Helpers for building knowledge sources from RAG configuration."""

from typing import Literal

from pydantic_ai.embeddings import Embedder

from models.config import RagConfiguration


def retrieval_mode(rag: RagConfiguration, name: str) -> set[Literal["tool", "auto"]]:
    """Return how a named source is exposed in a RAG configuration.

    Membership in ``retrieval.inline.sources`` adds ``auto``. Membership in
    ``retrieval.tool.sources`` adds ``tool``. A name in neither list yields
    an empty set.

    Args:
        rag: RAG configuration whose retrieval lists to read.
        name: Source name, a ``rag_id`` or ``"okp"``.

    Returns:
        The exposure modes configured for ``name``.

    """
    mode: set[Literal["tool", "auto"]] = set()
    if name in rag.retrieval.inline.sources:
        mode.add("auto")
    if name in rag.retrieval.tool.sources:
        mode.add("tool")
    return mode


def embedder_for_model(embedding_model: str) -> Embedder:
    """Build an embedder for a configured embedding model id.

    Ids that already include a provider prefix, such as
    ``openai:text-embedding-3-small``, are used as given. Other ids, such as
    ``sentence-transformers/all-mpnet-base-v2``, are local sentence-transformers
    models.

    Args:
        embedding_model: Embedding model id from a BYOK store.

    Returns:
        An embedder that defers loading the model until the first query.

    """
    if ":" not in embedding_model:
        embedding_model = f"sentence-transformers:{embedding_model}"
    return Embedder(embedding_model)

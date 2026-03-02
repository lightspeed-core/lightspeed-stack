"""Vector search utilities for query endpoints.

This module contains common functionality for performing vector searches
and processing RAG chunks that is shared between query_v2.py and streaming_query_v2.py.
"""

import traceback
from typing import Any, Optional
from urllib.parse import urljoin

from llama_stack_client import AsyncLlamaStackClient
from llama_stack_client.types.query_chunks_response import Chunk
from pydantic import AnyUrl

import constants
from configuration import configuration
from log import get_logger
from models.responses import ReferencedDocument
from utils.types import RAGChunk

logger = get_logger(__name__)


def _is_solr_enabled() -> bool:
    """Check if Solr is enabled in configuration."""
    return bool(configuration.solr and configuration.solr.enabled)


def _get_vector_store_ids(solr_enabled: bool) -> list[str]:
    """Get vector store IDs based on Solr configuration."""
    if solr_enabled:
        vector_store_ids = ["portal-rag"]
        logger.info(
            "Using portal-rag vector store for Solr query: %s",
            vector_store_ids,
        )
        return vector_store_ids
    return []


def _build_query_params(solr: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Build query parameters for vector search."""
    params = {
        "k": constants.VECTOR_SEARCH_DEFAULT_K,
        "score_threshold": constants.VECTOR_SEARCH_DEFAULT_SCORE_THRESHOLD,
        "mode": constants.VECTOR_SEARCH_DEFAULT_MODE,
    }
    logger.info("Initial params: %s", params)
    logger.info("solr: %s", solr)

    if solr:
        params["solr"] = solr
        logger.info("Final params with solr filters: %s", params)
    else:
        logger.info("No solr filters provided")

    logger.info("Final params being sent to vector_io.query: %s", params)
    return params


def _extract_document_metadata(
    chunk: Any,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract document ID, title, and reference URL from chunk metadata."""
    # 1) dict metadata
    metadata = getattr(chunk, "metadata", None) or {}
    doc_id = metadata.get("doc_id") or metadata.get("document_id")
    title = metadata.get("title")
    reference_url = metadata.get("reference_url")

    # 2) typed chunk_metadata
    if not doc_id:
        chunk_meta = getattr(chunk, "chunk_metadata", None)
        if chunk_meta is not None:
            if isinstance(chunk_meta, dict):
                doc_id = chunk_meta.get("doc_id") or chunk_meta.get("document_id")
                title = title or chunk_meta.get("title")
                reference_url = chunk_meta.get("reference_url")
            else:
                doc_id = getattr(chunk_meta, "doc_id", None) or getattr(
                    chunk_meta, "document_id", None
                )
                title = title or getattr(chunk_meta, "title", None)
                reference_url = getattr(chunk_meta, "reference_url", None)

    return doc_id, title, reference_url


def _process_chunks_for_documents(
    chunks: list[Any], offline: bool
) -> list[ReferencedDocument]:
    """Process chunks to extract referenced documents."""
    doc_ids_from_chunks = []
    metadata_doc_ids = set()

    for chunk in chunks:
        logger.info("Extract doc ids from chunk: %s", chunk)

        doc_id, title, reference_url = _extract_document_metadata(chunk)

        if not doc_id and not reference_url:
            continue

        # Build URL based on offline flag
        doc_url, reference_doc = _build_document_url(offline, doc_id, reference_url)

        if reference_doc and reference_doc not in metadata_doc_ids:
            metadata_doc_ids.add(reference_doc)
            # Convert string URL to AnyUrl if valid
            parsed_url: Optional[AnyUrl] = None
            if doc_url:
                try:
                    parsed_url = AnyUrl(doc_url)
                except Exception:  # pylint: disable=broad-exception-caught
                    parsed_url = None

            doc_ids_from_chunks.append(
                ReferencedDocument(
                    doc_title=title,
                    doc_url=parsed_url,
                )
            )

    logger.info(
        "Extracted %d unique document IDs from chunks",
        len(doc_ids_from_chunks),
    )
    return doc_ids_from_chunks


async def perform_vector_search(
    client: AsyncLlamaStackClient,
    query: str,
    solr: Optional[dict[str, Any]] = None,
) -> tuple[list[Any], list[float], list[ReferencedDocument], list[RAGChunk]]:
    """
    Perform vector search and extract RAG chunks and referenced documents.

    Args:
        client: The AsyncLlamaStackClient to use for the request
        query: The user's query
        solr: Solr query parameters

    Returns:
        Tuple containing:
        - retrieved_chunks: Raw chunks from vector store
        - retrieved_scores: Scores for each chunk
        - doc_ids_from_chunks: Referenced documents extracted from chunks
        - rag_chunks: Processed RAG chunks ready for use
    """
    retrieved_chunks: list[Chunk] = []
    retrieved_scores: list[float] = []
    doc_ids_from_chunks: list[ReferencedDocument] = []
    rag_chunks: list[RAGChunk] = []

    # Check if Solr is enabled in configuration
    if not _is_solr_enabled():
        logger.info("Solr vector IO is disabled, skipping vector search")
        return retrieved_chunks, retrieved_scores, doc_ids_from_chunks, rag_chunks

    # Get offline setting from configuration
    offline = configuration.solr.offline if configuration.solr else True

    try:
        vector_store_ids = _get_vector_store_ids(True)

        if vector_store_ids:
            vector_store_id = vector_store_ids[0]
            params = _build_query_params(solr)

            query_response = await client.vector_io.query(
                vector_store_id=vector_store_id,
                query=query,
                params=params,
            )

            logger.info("The query response total payload: %s", query_response)

            if query_response.chunks:
                retrieved_chunks = query_response.chunks
                retrieved_scores = (
                    query_response.scores if hasattr(query_response, "scores") else []
                )

                # Extract doc_ids from chunks for referenced_documents
                doc_ids_from_chunks = _process_chunks_for_documents(
                    query_response.chunks, offline
                )

                # Convert retrieved chunks to RAGChunk format
                rag_chunks = _convert_chunks_to_rag_format(
                    retrieved_chunks, retrieved_scores, offline
                )
                logger.info("Retrieved %d chunks from vector DB", len(rag_chunks))

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to query vector database for chunks: %s", e)
        logger.debug("Vector DB query error details: %s", traceback.format_exc())
        # Continue without RAG chunks

    return retrieved_chunks, retrieved_scores, doc_ids_from_chunks, rag_chunks


def _build_document_url(
    offline: bool, doc_id: Optional[str], reference_url: Optional[str]
) -> tuple[str, Optional[str]]:
    """
    Build document URL based on offline flag and available metadata.

    Args:
        offline: Whether to use offline mode (parent_id) or online mode (reference_url)
        doc_id: Document ID from chunk metadata
        reference_url: Reference URL from chunk metadata

    Returns:
        Tuple of (doc_url, reference_doc) where:
        - doc_url: The full URL for the document
        - reference_doc: The document reference used for deduplication
    """
    if offline:
        # Use parent/doc path
        reference_doc = doc_id
        doc_url = constants.MIMIR_DOC_URL + reference_doc if reference_doc else ""
    else:
        # Use reference_url if online
        reference_doc = reference_url or doc_id
        doc_url = (
            reference_doc
            if reference_doc and reference_doc.startswith("http")
            else (constants.MIMIR_DOC_URL + reference_doc if reference_doc else "")
        )

    return doc_url, reference_doc


def _convert_chunks_to_rag_format(
    retrieved_chunks: list[Any],
    retrieved_scores: list[float],
    offline: bool,
) -> list[RAGChunk]:
    """
    Convert retrieved chunks to RAGChunk format.

    Args:
        retrieved_chunks: Raw chunks from vector store
        retrieved_scores: Scores for each chunk
        offline: Whether to use offline mode for source URLs

    Returns:
        List of RAGChunk objects
    """
    rag_chunks = []

    for i, chunk in enumerate(retrieved_chunks):
        # Extract source from chunk metadata based on offline flag
        source = None
        if chunk.metadata:
            if offline:
                parent_id = chunk.metadata.get("parent_id")
                if parent_id:
                    source = urljoin(constants.MIMIR_DOC_URL, parent_id)
            else:
                source = chunk.metadata.get("reference_url")

        # Get score from retrieved_scores list if available
        score = retrieved_scores[i] if i < len(retrieved_scores) else None

        rag_chunks.append(
            RAGChunk(
                content=chunk.content,
                source=source,
                score=score,
            )
        )

    return rag_chunks


def format_rag_context_for_injection(
    rag_chunks: list[RAGChunk], max_chunks: int = 5
) -> str:
    """
    Format RAG context for injection into user message.

    Args:
        rag_chunks: List of RAG chunks to format
        max_chunks: Maximum number of chunks to include (default: 5)

    Returns:
        Formatted RAG context string ready for injection
    """
    if not rag_chunks:
        return ""

    context_chunks = []
    for chunk in rag_chunks[:max_chunks]:  # Limit to top chunks
        chunk_text = f"Source: {chunk.source or 'Unknown'}\n{chunk.content}"
        context_chunks.append(chunk_text)

    rag_context = "\n\nRelevant documentation:\n" + "\n\n".join(context_chunks)
    logger.info("Injecting %d RAG chunks into user message", len(context_chunks))

    return rag_context

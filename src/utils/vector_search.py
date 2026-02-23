"""Vector search utilities for query endpoints.

This module contains common functionality for performing vector searches
and processing RAG chunks that is shared between query_v2.py and streaming_query_v2.py.
"""

import asyncio
import traceback
from typing import Any, Optional
from urllib.parse import urljoin

from llama_stack_client import AsyncLlamaStackClient
from pydantic import AnyUrl

import constants
from configuration import AppConfig
from log import get_logger
from models.requests import QueryRequest
from models.responses import ReferencedDocument
from utils.responses import get_vector_store_ids
from utils.types import RAGChunk, RAGContext

logger = get_logger(__name__)


def _is_solr_enabled(configuration: AppConfig) -> bool:
    """Check if Solr is enabled in configuration."""
    return bool(configuration.rag.always.solr.enabled)


def _get_solr_vector_store_ids() -> list[str]:
    """Get vector store IDs based on Solr configuration."""
    vector_store_ids = [constants.SOLR_DEFAULT_VECTOR_STORE_ID]
    logger.info(
        "Using %s vector store for Solr query: %s",
        constants.SOLR_DEFAULT_VECTOR_STORE_ID,
        vector_store_ids,
    )
    return vector_store_ids


def _build_query_params(query_request: QueryRequest) -> dict:
    """Build query parameters for vector search."""
    params = {
        "k": constants.SOLR_VECTOR_SEARCH_DEFAULT_K,
        "score_threshold": constants.SOLR_VECTOR_SEARCH_DEFAULT_SCORE_THRESHOLD,
        "mode": constants.SOLR_VECTOR_SEARCH_DEFAULT_MODE,
    }
    logger.debug("Initial params: %s", params)
    logger.debug("query_request.solr: %s", query_request.solr)

    if query_request.solr:
        params["solr"] = query_request.solr
        logger.debug("Final params with solr filters: %s", params)
    else:
        logger.debug("No solr filters provided")

    logger.debug("Final params being sent to vector_io.query: %s", params)
    return params


def _extract_byok_rag_chunks(
    search_response: Any, vector_store_id: str, weight: float
) -> list[dict[str, Any]]:
    """Extract and weight result chunks from vector search for BYOK RAG.

    Args:
        search_response: Response from vector_io.query
        vector_store_id: ID of the vector store that produced these results
        weight: Score multiplier to apply to this store's results

    Returns:
        List of result dictionaries with weighted scores
    """
    result_chunks = []
    for chunk, score in zip(
        search_response.chunks, search_response.scores, strict=True
    ):
        weighted_score = score * weight
        doc_id = (
            chunk.metadata.get("document_id", chunk.chunk_id)
            if chunk.metadata
            else chunk.chunk_id
        )
        logger.debug(
            "  [%s] score=%.4f weighted=%.4f",
            vector_store_id,
            score,
            weighted_score,
        )
        result_chunks.append(
            {
                "content": chunk.content,
                "score": score,
                "weighted_score": weighted_score,
                "source": vector_store_id,
                "doc_id": doc_id,
                "metadata": chunk.metadata or {},
            }
        )
    return result_chunks


def _format_rag_context(rag_chunks: list[RAGChunk], query: str) -> str:
    """Format RAG chunks for pre-query context injection.

    This format is used for both BYOK RAG and Solr RAG chunks.
    Format is inspired by llama-stack file_search tool implementation.

    Args:
        rag_chunks: List of RAG chunks from pre-query sources (BYOK + Solr)
        query: The original search query

    Returns:
        Formatted string with RAG context metadata attributes
    """
    if not rag_chunks:
        return ""

    output = f"file_search found {len(rag_chunks)} chunks:\n"
    output += "BEGIN of file_search results.\n"

    for i, chunk in enumerate(rag_chunks, 1):
        # Build metadata text with source and score
        metadata_parts = []
        if chunk.source:
            metadata_parts.append(f"document_id: {chunk.source}")
        if chunk.score is not None:
            metadata_parts.append(f"score: {chunk.score:.4f}")

        metadata_text = ", ".join(metadata_parts)

        # Add additional attributes if present
        if chunk.attributes:
            metadata_text += f", attributes: {chunk.attributes}"

        # Format chunk with metadata and content
        output += f"[{i}] {metadata_text}\n{chunk.content}\n\n"

    output += "END of file_search results.\n"

    output += (
        f'The above results were retrieved to help answer the user\'s query: "{query}". '
        "Use them as supporting information only in answering this query. "
    )
    return output


async def _query_store_for_byok_rag(
    client: AsyncLlamaStackClient,
    vector_store_id: str,
    query: str,
    weight: float,
) -> list[dict[str, Any]]:
    """Query a single vector store for BYOK RAG.

    Args:
        client: AsyncLlamaStackClient for vector_io queries
        vector_store_id: ID of the vector store to query
        query: Search query string
        weight: Score multiplier to apply

    Returns:
        List of weighted result dictionaries, or empty list on error
    """
    try:
        search_response = await client.vector_io.query(
            vector_store_id=vector_store_id,
            query=query,
            params={
                "max_chunks": constants.BYOK_RAG_MAX_CHUNKS,
                "mode": "vector",
            },
        )
        return _extract_byok_rag_chunks(search_response, vector_store_id, weight)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to search '%s': %s", vector_store_id, e)
        return []


def _extract_solr_document_metadata(
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


def _process_byok_rag_chunks_for_documents(
    result_chunks: list[dict[str, Any]],
) -> list[ReferencedDocument]:
    """Process BYOK RAG result chunks to extract referenced documents.

    Args:
        result_chunks: Processed result dictionaries from BYOK RAG
                      (output of _extract_byok_rag_chunks)

    Returns:
        List of referenced documents extracted from BYOK RAG chunks
    """
    referenced_documents = []
    seen_doc_ids = set()

    for result in result_chunks:
        metadata = result.get("metadata", {})
        doc_id = result.get("doc_id") or metadata.get("document_id")
        title = metadata.get("title")
        reference_url = (
            metadata.get("reference_url")
            or metadata.get("doc_url")
            or metadata.get("docs_url")
        )

        if not doc_id and not reference_url:
            continue

        # Use doc_id or reference_url as deduplication key
        dedup_key = reference_url or doc_id
        if dedup_key and dedup_key not in seen_doc_ids:
            seen_doc_ids.add(dedup_key)

            # Build document URL
            parsed_url: Optional[AnyUrl] = None
            if reference_url:
                try:
                    parsed_url = AnyUrl(reference_url)
                except Exception:  # pylint: disable=broad-exception-caught
                    parsed_url = None

            referenced_documents.append(
                ReferencedDocument(
                    doc_title=title,
                    doc_url=parsed_url,
                    source=result.get("source"),  # Vector store ID
                )
            )

    logger.info(
        "Extracted %d unique documents from BYOK RAG",
        len(referenced_documents),
    )
    return referenced_documents


def _process_solr_chunks_for_documents(
    chunks: list[Any], offline: bool
) -> list[ReferencedDocument]:
    """Process Solr chunks to extract referenced documents.

    Args:
        chunks: Raw chunks from Solr vector store
        offline: Whether to use offline mode for URL construction

    Returns:
        List of referenced documents extracted from Solr chunks
    """
    doc_ids_from_chunks = []
    metadata_doc_ids = set()

    for chunk in chunks:
        logger.debug("Extract doc ids from chunk: %s", chunk)

        doc_id, title, reference_url = _extract_solr_document_metadata(chunk)

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
                    source="OKP Solr",
                )
            )

    logger.debug(
        "Extracted %d unique document IDs from Solr chunks",
        len(doc_ids_from_chunks),
    )
    return doc_ids_from_chunks


async def _fetch_byok_rag(
    client: AsyncLlamaStackClient,
    query: str,
    configuration: AppConfig,
    vector_store_ids: Optional[list[str]] = None,
) -> tuple[list[RAGChunk], list[ReferencedDocument]]:
    """Fetch chunks and documents from BYOK RAG sources.

    Args:
        client: The AsyncLlamaStackClient to use for the request
        query: The search query
        configuration: Application configuration
        vector_store_ids: Optional list of vector store IDs to query.
            If provided, only these stores will be queried. If None, all stores
            (excluding Solr) will be queried.

    Returns:
        Tuple containing:
        - rag_chunks: RAG chunks from BYOK RAG
        - referenced_documents: Documents referenced in BYOK RAG results
    """
    rag_chunks: list[RAGChunk] = []
    referenced_documents: list[ReferencedDocument] = []

    if not configuration.rag.always.byok.enabled:
        logger.info("Always RAG (BYOK) disabled, skipping BYOK RAG search")
        return rag_chunks, referenced_documents

    try:
        # Get score multiplier and rag_id mappings
        score_multiplier_mapping = configuration.score_multiplier_mapping
        rag_id_mapping = configuration.rag_id_mapping

        # Filter out Solr vector stores from available stores
        vector_store_ids_to_query = [
            vs_id
            for vs_id in await get_vector_store_ids(client, vector_store_ids)
            if vs_id != constants.SOLR_DEFAULT_VECTOR_STORE_ID
        ]

        # Query all vector stores in parallel
        results_per_store = await asyncio.gather(
            *[
                _query_store_for_byok_rag(
                    client,
                    vector_store_id,
                    query,
                    score_multiplier_mapping.get(vector_store_id, 1.0),
                )
                for vector_store_id in vector_store_ids_to_query
            ]
        )

        # Flatten, sort by weighted score, and take top results
        all_results: list[dict[str, Any]] = []
        for store_results in results_per_store:
            all_results.extend(store_results)
        all_results.sort(key=lambda x: x["weighted_score"], reverse=True)
        top_results = all_results[: constants.BYOK_RAG_MAX_CHUNKS]

        # Resolve source, log, and convert to RAGChunk in a single pass
        logger.info("Filtered top %d chunks from BYOK RAG", len(top_results))
        for result in top_results:
            result["source"] = rag_id_mapping.get(result["source"], result["source"])
            logger.debug(
                "  [%s] score=%.4f weighted=%.4f",
                result["source"],
                result["score"],
                result["weighted_score"],
            )
            rag_chunks.append(
                RAGChunk(
                    content=result["content"],
                    source=result["source"],
                    score=result["weighted_score"],
                    attributes=result.get("metadata", {}),
                )
            )

        # Extract referenced documents from BYOK RAG chunks (now with resolved sources)
        referenced_documents = _process_byok_rag_chunks_for_documents(top_results)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to perform BYOK RAG search: %s", e)
        logger.debug("BYOK RAG error details: %s", traceback.format_exc())

    return rag_chunks, referenced_documents


async def _fetch_solr_rag(
    client: AsyncLlamaStackClient,
    query_request: QueryRequest,
    configuration: AppConfig,
) -> tuple[list[RAGChunk], list[ReferencedDocument]]:
    """Fetch chunks and documents from Solr RAG source.

    Args:
        client: The AsyncLlamaStackClient to use for the request
        query_request: The user's query request
        configuration: Application configuration

    Returns:
        Tuple containing:
        - rag_chunks: RAG chunks from Solr
        - referenced_documents: Documents referenced in Solr results
    """
    rag_chunks: list[RAGChunk] = []
    referenced_documents: list[ReferencedDocument] = []

    if not _is_solr_enabled(configuration):
        logger.info("Solr vector IO is disabled, skipping Solr search")
        return rag_chunks, referenced_documents

    # Get offline setting from configuration
    offline = configuration.rag.always.solr.offline

    try:
        vector_store_ids = _get_solr_vector_store_ids()

        if vector_store_ids:
            # Assuming only one Solr vector store is registered
            vector_store_id = vector_store_ids[0]
            params = _build_query_params(query_request)

            query_response = await client.vector_io.query(
                vector_store_id=vector_store_id,
                query=query_request.query,
                params=params,
            )

            logger.debug("Solr query response: %s", query_response)

            if query_response.chunks:
                retrieved_scores = (
                    query_response.scores if hasattr(query_response, "scores") else []
                )

                # Limit to top N chunks
                top_chunks = query_response.chunks[: constants.SOLR_RAG_MAX_CHUNKS]
                top_scores = retrieved_scores[: constants.SOLR_RAG_MAX_CHUNKS]

                # Extract referenced documents from Solr chunks
                referenced_documents = _process_solr_chunks_for_documents(
                    top_chunks, offline
                )

                # Convert retrieved chunks to RAGChunk format
                rag_chunks = _convert_solr_chunks_to_rag_format(
                    top_chunks, top_scores, offline
                )
                logger.info(
                    "Filtered top %d chunks from Solr OKP RAG (%d were retrieved)",
                    constants.SOLR_RAG_MAX_CHUNKS,
                    len(rag_chunks),
                )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to query Solr for chunks: %s", e)
        logger.debug("Solr query error details: %s", traceback.format_exc())

    return rag_chunks, referenced_documents


async def build_rag_context(
    client: AsyncLlamaStackClient,
    query_request: QueryRequest,
    configuration: AppConfig,
) -> RAGContext:
    """Build RAG context by fetching and merging chunks from all enabled sources.

    Enabled sources can be BYOK and/or Solr OKP.

    Args:
        client: The AsyncLlamaStackClient to use for the request
        query_request: The user's query request
        configuration: Application configuration

    Returns:
        RAGContext containing formatted context text and referenced documents
    """
    # Fetch from all enabled RAG sources in parallel
    byok_chunks_task = _fetch_byok_rag(
        client, query_request.query, configuration, query_request.vector_store_ids
    )
    solr_chunks_task = _fetch_solr_rag(client, query_request, configuration)

    (byok_chunks, byok_docs), (solr_chunks, solr_docs) = await asyncio.gather(
        byok_chunks_task, solr_chunks_task
    )

    # Merge chunks from all sources (BYOK + Solr)
    context_chunks = byok_chunks + solr_chunks

    context_text = _format_rag_context(context_chunks, query_request.query)

    logger.debug("=" * 80)
    logger.debug("RAG context built for pre-query injection:")
    logger.debug(context_text)
    logger.debug("=" * 80)

    # Merge referenced documents from all sources (BYOK + Solr)
    top_documents = byok_docs + solr_docs

    return RAGContext(
        context_text=context_text,
        rag_chunks=context_chunks,
        referenced_documents=top_documents,
    )


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


def _convert_solr_chunks_to_rag_format(
    retrieved_chunks: list[Any],
    retrieved_scores: list[float],
    offline: bool,
) -> list[RAGChunk]:
    """
    Convert retrieved chunks to RAGChunk format for Solr OKP.

    Args:
        retrieved_chunks: Raw chunks from vector store
        retrieved_scores: Scores for each chunk
        offline: Whether to use offline mode for source URLs

    Returns:
        List of RAGChunk objects
    """
    rag_chunks = []

    for i, chunk in enumerate(retrieved_chunks):
        # Build attributes with document metadata
        attributes = {}

        # Legacy logic: extract doc_url from chunk metadata based on offline flag
        if chunk.metadata:
            if offline:
                parent_id = chunk.metadata.get("parent_id")
                if parent_id:
                    attributes["doc_url"] = urljoin(constants.MIMIR_DOC_URL, parent_id)
            else:
                reference_url = chunk.metadata.get("reference_url")
                if reference_url:
                    attributes["doc_url"] = reference_url

        # For Solr chunks, also extract from chunk_metadata
        if hasattr(chunk, "chunk_metadata") and chunk.chunk_metadata:
            if hasattr(chunk.chunk_metadata, "document_id"):
                doc_id = chunk.chunk_metadata.document_id
                attributes["document_id"] = doc_id
                # Build URL if not already set
                if "doc_url" not in attributes and offline and doc_id:
                    attributes["doc_url"] = urljoin(constants.MIMIR_DOC_URL, doc_id)

        # Get score from retrieved_scores list if available
        score = retrieved_scores[i] if i < len(retrieved_scores) else None

        rag_chunks.append(
            RAGChunk(
                content=chunk.content,
                source="OKP Solr",  # Hardcoded source for Solr chunks
                score=score,
                attributes=attributes if attributes else None,
            )
        )

    return rag_chunks

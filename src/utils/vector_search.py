"""Vector search utilities for query endpoints.

This module contains common functionality for performing vector searches
and processing RAG chunks that is shared between query_v2.py and streaming_query_v2.py.
"""

import asyncio
import traceback
from typing import Any, Optional, cast

from llama_stack_api.openai_responses import (
    OpenAIResponseMessage as ResponseMessage,
)
from llama_stack_client import AsyncLlamaStackClient
from pydantic import AnyUrl

import constants
from configuration import configuration
from log import get_logger
from models.responses import ReferencedDocument
from utils.responses import resolve_vector_store_ids
from utils.types import RAGChunk, RAGContext, RAGContextParams, ResponseInput

logger = get_logger(__name__)


def _get_okp_base_url() -> AnyUrl:
    """Return OKP document base URL from configuration (rhokp_url), or default if unset.

    Returns:
        Parsed base URL as ``AnyUrl``.
    """
    rhokp = configuration.okp.rhokp_url
    if rhokp is None:
        return AnyUrl(constants.RH_SERVER_OKP_DEFAULT_URL)
    return AnyUrl(str(rhokp))


def _is_solr_enabled() -> bool:
    """Check if Solr is enabled for inline RAG in configuration."""
    return configuration.inline_solr_enabled


def _get_solr_vector_store_ids() -> list[str]:
    """Get vector store IDs based on Solr configuration."""
    vector_store_ids = [constants.SOLR_DEFAULT_VECTOR_STORE_ID]
    logger.info(
        "Using %s vector store for OKP query: %s",
        constants.SOLR_DEFAULT_VECTOR_STORE_ID,
        vector_store_ids,
    )
    return vector_store_ids


def _build_query_params(solr: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Build query parameters for vector search."""
    params = {
        "k": constants.SOLR_VECTOR_SEARCH_DEFAULT_K,
        "score_threshold": constants.SOLR_VECTOR_SEARCH_DEFAULT_SCORE_THRESHOLD,
        "mode": constants.SOLR_VECTOR_SEARCH_DEFAULT_MODE,
    }
    logger.debug("Initial params: %s", params)
    logger.debug("query_request.solr: %s", solr)

    if solr:
        params["solr"] = solr
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
        logger.debug(
            "Extracting doc ids from chunk id: %s", getattr(chunk, "chunk_id", None)
        )

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
                    source=constants.OKP_RAG_ID,
                )
            )

    logger.debug(
        "Extracted %d unique document IDs from OKP chunks",
        len(doc_ids_from_chunks),
    )
    return doc_ids_from_chunks


async def _fetch_byok_rag(
    client: AsyncLlamaStackClient,
    query: str,
    vector_store_ids: Optional[list[str]] = None,  # User-facing
    no_tools: bool = False,
) -> tuple[list[RAGChunk], list[ReferencedDocument]]:
    # pylint: disable=too-many-locals
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

    # When no_tools=True and vector_store_ids is provided, use it (even if empty).
    # Otherwise, use config inline.
    if no_tools and vector_store_ids is not None:
        rag_ids_to_query = vector_store_ids
    else:
        rag_ids_to_query = configuration.configuration.rag.inline

    # Translate user-facing rag_ids to llama-stack ids
    vector_store_ids_to_query: list[str] = resolve_vector_store_ids(
        rag_ids_to_query, configuration.configuration.byok_rag
    )

    # Request-level override: filter out Solr store, use the rest
    vector_store_ids_to_query = [
        vs_id
        for vs_id in vector_store_ids_to_query
        if vs_id != constants.SOLR_DEFAULT_VECTOR_STORE_ID
    ]

    # If inline byok stores are not defined, we disable the inline RAG for backward compatibility
    if not vector_store_ids_to_query:
        logger.info("No inline BYOK RAG sources configured, skipping BYOK RAG search")
        return rag_chunks, referenced_documents

    try:
        # Get score multiplier and rag_id mappings
        score_multiplier_mapping = configuration.score_multiplier_mapping
        rag_id_mapping = configuration.rag_id_mapping

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
    query: str,
    solr: Optional[dict[str, Any]] = None,
) -> tuple[list[RAGChunk], list[ReferencedDocument]]:
    """Fetch chunks and documents from Solr RAG source.

    Args:
        client: The AsyncLlamaStackClient to use for the request
        query: The user's query
        solr: Solr query parameters

    Returns:
        Tuple containing:
        - rag_chunks: RAG chunks from Solr
        - referenced_documents: Documents referenced in Solr results
    """
    rag_chunks: list[RAGChunk] = []
    referenced_documents: list[ReferencedDocument] = []

    if not _is_solr_enabled():
        logger.info("OKP vector IO is disabled, skipping OKP search")
        return rag_chunks, referenced_documents

    # Get offline setting from configuration
    offline = configuration.okp.offline

    try:
        vector_store_ids = _get_solr_vector_store_ids()

        if vector_store_ids:
            # Assuming only one Solr vector store is registered
            vector_store_id = vector_store_ids[0]
            params = _build_query_params(solr)

            query_response = await client.vector_io.query(
                vector_store_id=vector_store_id,
                query=query,
                params=params,
            )

            logger.debug(
                "OKP query returned %d chunks", len(query_response.chunks or [])
            )

            if query_response.chunks:
                retrieved_scores = (
                    query_response.scores if hasattr(query_response, "scores") else []
                )

                # Limit to top N chunks
                top_chunks = query_response.chunks[: constants.OKP_RAG_MAX_CHUNKS]
                top_scores = retrieved_scores[: constants.OKP_RAG_MAX_CHUNKS]

                # Extract referenced documents from Solr chunks
                referenced_documents = _process_solr_chunks_for_documents(
                    top_chunks, offline
                )

                # Convert retrieved chunks to RAGChunk format
                rag_chunks = _convert_solr_chunks_to_rag_format(
                    top_chunks, top_scores, offline
                )
                logger.debug(
                    "Filtered top %d chunks from OKP RAG (%d were retrieved)",
                    constants.OKP_RAG_MAX_CHUNKS,
                    len(rag_chunks),
                )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to query OKP for chunks: %s", e)
        logger.debug("OKP query error details: %s", traceback.format_exc())

    return rag_chunks, referenced_documents


async def build_rag_context(
    client: AsyncLlamaStackClient,
    params: RAGContextParams,
) -> RAGContext:
    """Build RAG context by fetching and merging chunks from all enabled sources.

    Enabled sources can be BYOK and/or Solr OKP.

    Args:
        client: The AsyncLlamaStackClient to use for the request
        params: RAG context parameters (moderation_decision, query,
            vector_store_ids, solr, no_tools)

    Returns:
        RAGContext containing formatted context text and referenced documents
    """
    if params.moderation_decision == "blocked":
        return RAGContext()

    # Fetch from all enabled RAG sources in parallel
    byok_chunks_task = _fetch_byok_rag(
        client, params.query, params.vector_store_ids, params.no_tools
    )
    solr_chunks_task = _fetch_solr_rag(client, params.query, params.solr)

    (byok_chunks, byok_docs), (solr_chunks, solr_docs) = await asyncio.gather(
        byok_chunks_task, solr_chunks_task
    )

    # Merge chunks from all sources (BYOK + Solr)
    context_chunks = byok_chunks + solr_chunks

    context_text = _format_rag_context(context_chunks, params.query)

    logger.debug(
        "Inline RAG context built: %d chunks, %d characters",
        len(context_chunks),
        len(context_text),
    )

    # Merge referenced documents from all sources (BYOK + Solr)
    top_documents = byok_docs + solr_docs

    return RAGContext(
        context_text=context_text,
        rag_chunks=context_chunks,
        referenced_documents=top_documents,
    )


def _join_okp_doc_url(base_url: AnyUrl, reference: Optional[str]) -> str:
    """Build a well-formed document URL from base and reference.

    If reference is None or empty, returns ''.
    If reference already starts with 'http', returns reference unchanged.
    Otherwise normalizes ``base_url`` to end with a single '/', strips any leading
    '/' from reference, and concatenates.

    Args:
        base_url: OKP base URL.
        reference: Document path or full URL.

    Returns:
        Well-formed doc_url string.
    """
    if not reference:
        return ""
    if reference.startswith("http"):
        return reference
    base = str(base_url).rstrip("/") + "/"
    ref = reference.lstrip("/")
    return base + ref


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
    base_url = _get_okp_base_url()
    reference_doc = doc_id if offline else (reference_url or doc_id)
    doc_url = _join_okp_doc_url(base_url, reference_doc)
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
                    attributes["doc_url"] = _join_okp_doc_url(
                        _get_okp_base_url(), parent_id
                    )
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
                    attributes["doc_url"] = _join_okp_doc_url(
                        _get_okp_base_url(), doc_id
                    )

        # Get score from retrieved_scores list if available
        score = retrieved_scores[i] if i < len(retrieved_scores) else None

        rag_chunks.append(
            RAGChunk(
                content=chunk.content,
                source=constants.OKP_RAG_ID,
                score=score,
                attributes=attributes if attributes else None,
            )
        )

    return rag_chunks


def append_inline_rag_context_to_responses_input(
    input_value: ResponseInput,
    inline_rag_context_text: str,
) -> ResponseInput:
    """Append inline RAG context to Responses API input.

    If input is str, appends the context text.
    If input is a sequence of items, appends the context to the text of the first user message.
    If there is no user message, returns the input unchanged.

    Parameters:
        input_value: The request input (string or list of ResponseItem).
        inline_rag_context_text: RAG context string to inject.

    Returns:
        The same type as input_value, with context merged in.
    """
    if not inline_rag_context_text:
        return input_value
    if isinstance(input_value, str):
        return input_value + "\n\n" + inline_rag_context_text
    for item in input_value:
        if item.type != "message" or item.role != "user":
            continue
        message = cast(ResponseMessage, item)
        content = message.content
        if isinstance(content, str):
            message.content = content + "\n\n" + inline_rag_context_text
            return input_value
        for part in content:
            if part.type == "input_text":
                part.text = part.text + "\n\n" + inline_rag_context_text
                return input_value
    return input_value

"""OKP-over-MCP RAG retriever.

Fetches OKP RAG context from the RHOKP MCP server and maps the returned
documents to the backend-neutral :class:`~models.common.turn_summary.RAGChunk`
and :class:`~models.common.turn_summary.ReferencedDocument` models. This is the
Pydantic-AI analog of the OGX/Solr ``_fetch_okp_rag`` path; the two are
interchangeable at the ``build_rag_context`` fork and produce the same output
contract.
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Any, Optional
from urllib.parse import urljoin

from pydantic import AnyUrl, ValidationError

import constants
from configuration import configuration
from log import get_logger
from models.common.query import OkpFilter
from models.common.turn_summary import RAGChunk, ReferencedDocument
from pydantic_ai_lightspeed.retrieval.okp_mcp._client import call_okp_search

logger = get_logger(__name__)


class OkpMcpRetriever:  # pylint: disable=too-many-instance-attributes
    """Retrieve OKP RAG context from the RHOKP MCP server.

    Attributes:
        url: RHOKP MCP endpoint (streamable HTTP).
        tool_name: Name of the MCP search tool to call.
        max_chunks: Maximum number of chunks to keep from the response.
        offline: When True, build document URLs from ``source_path``; when
            False, use ``online_source_url``.
        doc_base_url: Base URL used to build offline document URLs.
        headers: Optional static request headers (e.g. authorization).
        timeout: Optional per-request timeout in seconds.
        product: Optional product filter passed to the MCP search tool.
        product_version: Optional product-version filter passed to the MCP
            search tool.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        url: str,
        tool_name: str,
        max_chunks: int,
        offline: bool,
        doc_base_url: str,
        headers: Optional[dict[str, str]] = None,
        timeout: Optional[float] = None,
        product: Optional[str] = None,
        product_version: Optional[str] = None,
    ) -> None:
        """Initialize the retriever with an explicit configuration.

        Prefer :meth:`from_configuration` for the runtime instance; the explicit
        constructor exists mainly for testing.
        """
        self.url = url
        self.tool_name = tool_name
        self.max_chunks = max_chunks
        self.offline = offline
        self.doc_base_url = doc_base_url
        self.headers = headers
        self.timeout = timeout
        self.product = product
        self.product_version = product_version

    @classmethod
    def from_configuration(cls) -> OkpMcpRetriever:
        """Build a retriever from the loaded global configuration.

        Reads ``rag.okp`` and ``rag.okp.mcp``. Falls back to the constant
        defaults for the MCP URL and the document base URL when unset.

        Returns:
            OkpMcpRetriever: Configured retriever instance.
        """
        okp = configuration.okp
        mcp = okp.mcp
        url = (
            str(mcp.url)
            if mcp.url is not None
            else constants.RH_SERVER_OKP_MCP_DEFAULT_URL
        )
        doc_base_url = (
            str(okp.rhokp_url)
            if okp.rhokp_url is not None
            else constants.RH_SERVER_OKP_DEFAULT_URL
        )
        headers = mcp.resolved_authorization_headers or None
        timeout = float(mcp.timeout) if mcp.timeout is not None else None
        return cls(
            url=url,
            tool_name=mcp.tool_name,
            max_chunks=mcp.max_chunks,
            offline=okp.offline,
            doc_base_url=doc_base_url,
            headers=headers,
            timeout=timeout,
            product=mcp.product,
            product_version=mcp.product_version,
        )

    def _resolve_search_combos(
        self, okp: Optional[OkpFilter]
    ) -> list[tuple[Optional[str], Optional[str]]]:
        """Resolve the (product, product_version) pairs to search.

        The RHOKP MCP ``search`` tool takes a scalar product/version, so a
        multi-product/multi-version query-time filter expands into one search
        per (product, version) pair. A query-time filter fully overrides the
        launch-time config defaults; when absent, the configured defaults (which
        may both be None) are used.

        Parameters:
            okp: Optional query-time OKP filter.

        Returns:
            A non-empty list of ``(product, product_version)`` pairs. Either
            element may be None (meaning "unfiltered on that facet").
        """
        if okp is not None and okp.products:
            combos: list[tuple[Optional[str], Optional[str]]] = []
            for entry in okp.products:
                if entry.versions:
                    combos.extend((entry.product, v) for v in entry.versions)
                else:
                    combos.append((entry.product, None))
            return combos
        return [(self.product, self.product_version)]

    async def fetch(
        self, query: str, okp: Optional[OkpFilter] = None
    ) -> tuple[list[RAGChunk], list[ReferencedDocument]]:
        """Fetch chunks and referenced documents from the RHOKP MCP server.

        When ``okp`` selects multiple products/versions, one search is issued per
        (product, version) pair and the results are merged, deduplicated, sorted
        by score, and capped at ``max_chunks``. Any transport or tool error on an
        individual search is caught and logged; the remaining searches still
        contribute, so RAG retrieval degrades gracefully rather than failing the
        request.

        Parameters:
            query: The raw user query string.
            okp: Optional query-time OKP filter overriding the configured
                product/version defaults.

        Returns:
            A tuple of ``(rag_chunks, referenced_documents)``. Both lists are
            empty when the server returns no usable documents or every call
            fails.
        """
        rows = min(self.max_chunks, constants.OKP_MCP_MAX_ROWS)
        combos = self._resolve_search_combos(okp)
        results = await asyncio.gather(
            *(
                call_okp_search(
                    url=self.url,
                    tool_name=self.tool_name,
                    query=query,
                    rows=rows,
                    headers=self.headers,
                    timeout=self.timeout,
                    product=product,
                    product_version=product_version,
                )
                for product, product_version in combos
            ),
            return_exceptions=True,
        )

        docs: list[dict[str, Any]] = []
        for combo, result in zip(combos, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "Failed to query OKP MCP server for chunks (product=%r, "
                    "product_version=%r): %s",
                    combo[0],
                    combo[1],
                    result,
                )
                logger.debug(
                    "OKP MCP query error details: %s",
                    "".join(traceback.format_exception(result)),
                )
                continue
            docs.extend(self._extract_docs(result))

        if not docs:
            logger.debug("OKP MCP returned no documents for query")
            return [], []

        docs = self._merge_docs(docs)[: self.max_chunks]
        rag_chunks = self._to_rag_chunks(docs)
        referenced_documents = self._to_referenced_documents(docs)
        logger.debug(
            "OKP MCP retrieval: %d chunks, %d documents (from %d search(es))",
            len(rag_chunks),
            len(referenced_documents),
            len(combos),
        )
        return rag_chunks, referenced_documents

    @staticmethod
    def _merge_docs(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Merge documents from one or more searches into a ranked, unique list.

        Sorts by descending score (missing scores rank last) and deduplicates
        exact repeats — the same chunk of the same document returned by
        overlapping searches — while preserving distinct chunks of one document.

        Parameters:
            docs: Concatenated document mappings from all issued searches.

        Returns:
            Documents sorted by descending score with exact duplicates removed.
        """
        def _score(doc: dict[str, Any]) -> float:
            value = doc.get("score")
            return float(value) if isinstance(value, (int, float)) else float("-inf")

        docs_sorted = sorted(docs, key=_score, reverse=True)
        seen: set[tuple[Any, Any]] = set()
        merged: list[dict[str, Any]] = []
        for doc in docs_sorted:
            key = (doc.get("doc_id"), doc.get("chunk"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(doc)
        return merged

    @staticmethod
    def _extract_docs(result: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract the ``response.docs`` list from a search tool result.

        Parameters:
            result: The structured content returned by the MCP search tool.

        Returns:
            The list of document mappings, or an empty list when the payload is
            missing or malformed.
        """
        response = result.get("response")
        if not isinstance(response, dict):
            return []
        docs = response.get("docs")
        if not isinstance(docs, list):
            return []
        return [doc for doc in docs if isinstance(doc, dict)]

    def _build_doc_url(self, doc: dict[str, Any]) -> Optional[str]:
        """Build a document URL for a single document.

        Uses ``source_path`` (joined onto the OKP base URL) when offline, or the
        absolute ``online_source_url`` when online.

        Parameters:
            doc: A single document mapping from the MCP search result.

        Returns:
            The document URL string, or None when no URL can be built.
        """
        if self.offline:
            source_path = doc.get("source_path")
            if source_path:
                return urljoin(self.doc_base_url, source_path)
            return None
        online_source_url = doc.get("online_source_url")
        return online_source_url or None

    def _to_rag_chunks(self, docs: list[dict[str, Any]]) -> list[RAGChunk]:
        """Convert MCP documents to ``RAGChunk`` objects.

        Documents without chunk content are skipped.

        Parameters:
            docs: Document mappings from the MCP search result.

        Returns:
            List of ``RAGChunk`` labelled with the OKP source id.
        """
        rag_chunks: list[RAGChunk] = []
        for doc in docs:
            content = doc.get("chunk")
            if not content:
                continue
            attributes: dict[str, Any] = {}
            doc_url = self._build_doc_url(doc)
            if doc_url:
                attributes["doc_url"] = doc_url
            for key in ("doc_id", "title", "product", "product_version"):
                value = doc.get(key)
                if value is not None:
                    attributes[key] = value
            if doc.get("doc_id") is not None:
                attributes["document_id"] = doc["doc_id"]

            rag_chunks.append(
                RAGChunk(
                    content=content,
                    source=constants.OKP_RAG_ID,
                    score=doc.get("score"),
                    attributes=attributes or None,
                )
            )
        return rag_chunks

    def _to_referenced_documents(
        self, docs: list[dict[str, Any]]
    ) -> list[ReferencedDocument]:
        """Extract unique referenced documents from MCP documents.

        Deduplicates by document URL (falling back to ``doc_id``), mirroring the
        Solr path so the downstream merge/dedup stays source-agnostic.

        Parameters:
            docs: Document mappings from the MCP search result.

        Returns:
            List of unique ``ReferencedDocument`` objects.
        """
        referenced_documents: list[ReferencedDocument] = []
        seen: set[str] = set()
        for doc in docs:
            doc_id = doc.get("doc_id")
            doc_url = self._build_doc_url(doc)
            dedup_key = doc_url or doc_id
            if not dedup_key or dedup_key in seen:
                continue
            seen.add(dedup_key)

            parsed_url: Optional[AnyUrl] = None
            if doc_url:
                try:
                    parsed_url = AnyUrl(doc_url)
                except ValidationError:
                    parsed_url = None

            referenced_documents.append(
                ReferencedDocument(
                    doc_title=doc.get("title"),
                    doc_url=parsed_url,
                    source=constants.OKP_RAG_ID,
                    document_id=doc_id,
                )
            )
        return referenced_documents

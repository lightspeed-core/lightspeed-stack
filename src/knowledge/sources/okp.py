"""OKP knowledge source backed by the OKP MCP server.

Searches the server's ``search`` tool (hybrid keyword match plus semantic
rerank) and maps returned Solr documents to :class:`KnowledgeMatch`.
This source does not embed queries and does not talk to Solr or OGX
``vector_io``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import httpx
from mcp import ClientSession, McpError
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult

from knowledge.sources.base import KnowledgeSource
from knowledge.types import KnowledgeMatch, KnowledgeReadiness
from log import get_logger
from utils.mcp.mcp_headers import ensure_bearer_prefix

logger = get_logger(__name__)


@dataclass(frozen=True)
class OkpProductFilter:
    """One product restriction for the OKP MCP ``search`` tool.

    The server matches ``product`` exactly and OR-combines ``versions``.
    An empty ``versions`` tuple matches that product at any version.
    Several filters on one source are OR-combined.

    Attributes:
        product: Product slug, for example ``openshift_container_platform``.
        versions: Versions to include, for example ``("4.19", "4.20")``.

    """

    product: str
    versions: tuple[str, ...] = ()

    def as_tool_argument(self) -> dict[str, Any]:
        """Return this filter as an MCP ``products`` entry.

        Returns:
            A ``product`` object. ``versions`` is omitted when empty so the
            server matches every version of the product.

        """
        argument: dict[str, Any] = {"product": self.product}
        if self.versions:
            argument["versions"] = list(self.versions)
        return argument


@dataclass
class OkpKnowledgeSource(KnowledgeSource):
    """Knowledge source that calls the OKP MCP ``search`` tool.

    Each search opens its own streamable-HTTP MCP session, so concurrent
    searches do not share a connection. The server combines keyword matching
    with semantic reranking; this tool has no separate search-mode argument.
    Product restrictions use :class:`OkpProductFilter` rather than a Solr
    filter string.

    When ``offline`` is true, citations use ``source_path``. Otherwise they
    use ``online_source_url``, then ``source_path``.

    Attributes:
        url: MCP endpoint, for example ``https://host.example/mcp``.
        headers: HTTP headers forwarded on the MCP connection.
        rows: Maximum documents to request. The server accepts 1 through 20.
        products: Optional product restrictions, OR-combined by the server.
        offline: Whether citations use the offline document path.

    """

    url: str
    headers: dict[str, str] = field(default_factory=dict)
    rows: int = 5
    products: tuple[OkpProductFilter, ...] = ()
    offline: bool = True

    def __post_init__(self) -> None:
        """Reject a row count the search tool will not accept.

        The MCP ``search`` tool accepts 1 through 20 rows.
        """
        if self.rows < 1 or self.rows > 20:
            raise ValueError(f"rows must be between 1 and 20, got {self.rows}")

    async def search(self, prompt: str) -> list[KnowledgeMatch]:
        """Search OKP and return matches in server order.

        Args:
            prompt: Natural-language query sent as the tool's ``query``.

        Returns:
            Matching documents, at most ``rows`` of them. Documents without
            chunk text are dropped.

        Raises:
            RuntimeError: The tool failed or the result has no document list.

        """
        arguments: dict[str, Any] = {"query": prompt, "rows": self.rows}
        if self.products:
            arguments["products"] = [
                product.as_tool_argument() for product in self.products
            ]
        async with self._connect() as session:
            result = await session.call_tool(
                "search",
                arguments=arguments,
                read_timeout_seconds=timedelta(seconds=60),
            )
        matches: list[KnowledgeMatch] = []
        for doc in self._documents(result):
            match = self._match(doc)
            if match is not None:
                matches.append(match)
        matches = matches[: self.rows]
        logger.info("OKP MCP search returned %d document(s)", len(matches))
        return matches

    def _documents(self, result: CallToolResult) -> list[dict[str, Any]]:
        """Return the Solr documents from a search tool result.

        Args:
            result: Tool result from the OKP MCP server.

        Returns:
            Document objects from ``response.docs``.

        Raises:
            RuntimeError: The tool failed or the result has no document list.

        """
        if result.isError:
            texts: list[str] = []
            for block in result.content:
                text = getattr(block, "text", None)
                if isinstance(text, str) and text:
                    texts.append(text)
            raise RuntimeError("; ".join(texts) or "OKP MCP search failed")

        payload: Any = result.structuredContent
        if not isinstance(payload, dict):
            payload = None
            for block in result.content:
                text = getattr(block, "text", None)
                if not isinstance(text, str) or not text.strip():
                    continue
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    payload = parsed
                    break
        if not isinstance(payload, dict):
            raise RuntimeError("OKP MCP search returned no structured result")

        response = payload.get("response")
        if not isinstance(response, dict):
            raise RuntimeError("OKP MCP search result is missing response")
        docs = response.get("docs")
        if not isinstance(docs, list):
            raise RuntimeError("OKP MCP search result is missing response.docs")
        logger.debug("OKP MCP search numFound=%s", response.get("numFound"))
        return [doc for doc in docs if isinstance(doc, dict)]

    def _match(self, doc: dict[str, Any]) -> KnowledgeMatch | None:
        """Map one Solr document onto a knowledge match.

        Args:
            doc: One entry from ``response.docs``.

        Returns:
            The match, or ``None`` when the document has no chunk text.

        """
        chunk = doc.get("chunk")
        if not isinstance(chunk, str) or not chunk.strip():
            return None

        citation = (
            doc.get("source_path")
            if self.offline
            else doc.get("online_source_url") or doc.get("source_path")
        ) or None

        metadata: dict[str, Any] = {
            key: doc[key]
            for key in (
                "category",
                "content_type",
                "doc_id",
                "headings",
                "id",
                "online_source_url",
                "originalScore()",
                "product",
                "product_version",
                "source_path",
                "title",
            )
            if doc.get(key) is not None
        }

        return KnowledgeMatch(
            content=chunk,
            score=float(doc["score"]),
            id=str(doc["id"]),
            source=citation,
            metadata=metadata,
        )

    async def readiness(self) -> KnowledgeReadiness:
        """Report whether the MCP server exposes the ``search`` tool.

        Returns:
            ``ready`` when ``search`` is listed, otherwise ``not_ready``.
            Connection failures are reported as ``not_ready`` and are not
            raised.

        """
        try:
            async with self._connect() as session:
                listed = await session.list_tools()
        except (httpx.HTTPError, McpError, ExceptionGroup) as exc:
            detail: BaseException = exc
            while isinstance(detail, ExceptionGroup):
                nested = detail.exceptions
                if not nested:
                    break
                detail = nested[0]
            return KnowledgeReadiness(
                status="not_ready",
                message=f"OKP MCP server at {self.url} is unreachable: {detail}",
            )
        names = {tool.name for tool in listed.tools}
        if "search" not in names:
            return KnowledgeReadiness(
                status="not_ready",
                message="OKP MCP server does not expose the 'search' tool",
            )
        return KnowledgeReadiness(
            status="ready",
            message="OKP MCP search tool is available",
        )

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[ClientSession]:
        """Open an initialized streamable-HTTP session to this source's server.

        Yields:
            An MCP client session. It is closed when the block exits.

        """
        headers = dict(self.headers)
        for name, value in headers.items():
            if name.lower() == "authorization" and value:
                headers[name] = ensure_bearer_prefix(value)
        timeout = httpx.Timeout(30.0, read=60.0)
        async with httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        ) as http_client:
            async with streamable_http_client(self.url, http_client=http_client) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session

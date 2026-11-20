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
from typing import Any, Optional, Self

import httpx
from mcp import ClientSession, McpError
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult

from constants import OKP_RAG_ID, RH_SERVER_OKP_DEFAULT_URL
from knowledge.sources.base import KnowledgeSource
from knowledge.sources.utils import retrieval_mode
from knowledge.types import KnowledgeMatch, KnowledgeReadiness
from log import get_logger
from models.config import RagConfiguration
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

    When ``offline`` is true, citations join ``base_url`` with
    ``source_path``. Otherwise they use ``online_source_url``.

    Attributes:
        base_url: OKP service base URL, for example ``https://host.example``.
            The MCP endpoint is ``{base_url}/mcp``.
        headers: HTTP headers forwarded on the MCP connection.
        rows: Maximum documents to request. The server accepts 1 through 20.
        products: Optional product restrictions, OR-combined by the server.
        offline: Whether citations use the offline document path.

    """

    base_url: str
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

    @classmethod
    def from_rag_configuration(cls, rag: RagConfiguration) -> Optional[Self]:
        """Build the OKP source when retrieval configuration includes it.

        Args:
            rag: RAG configuration. OKP is built only when ``"okp"`` is listed
                in inline or tool retrieval sources. ``okp.max_chunks`` becomes
                ``rows``, ``okp.offline`` selects the citation path, and
                ``okp.rhokp_url`` is the MCP endpoint.

        Returns:
            The OKP source, or None when OKP is not a retrieval source.

        """
        mode = retrieval_mode(rag, OKP_RAG_ID)
        if not mode:
            return None
        url = (
            str(rag.okp.rhokp_url)
            if rag.okp.rhokp_url is not None
            else RH_SERVER_OKP_DEFAULT_URL
        )
        return cls(
            name=OKP_RAG_ID,
            base_url=url,
            rows=rag.okp.max_chunks,
            offline=rag.okp.offline,
            mode=mode,
        )

    @property
    def mcp_url(self) -> str:
        """Return the streamable-HTTP endpoint for this OKP service.

        Returns:
            ``base_url`` with a single ``/mcp`` path appended.

        """
        return f"{self.base_url.rstrip('/')}/mcp"

    async def search(self, prompt: str) -> list[KnowledgeMatch]:
        """Search OKP and return matches in server order.

        Args:
            prompt: Natural-language query sent as the tool's ``query``.

        Returns:
            Matching documents, at most ``rows`` of them. Documents without
            chunk text are dropped. A failed tool call or a result without a
            document list contributes no matches.

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
            Document objects from ``response.docs``. An empty list when the
            tool failed or the result has no document list.

        """
        if result.isError:
            texts: list[str] = []
            for block in result.content:
                text = getattr(block, "text", None)
                if isinstance(text, str) and text:
                    texts.append(text)
            logger.warning("%s", "; ".join(texts) or "OKP MCP search failed")
            return []

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
            logger.warning("OKP MCP search returned no structured result")
            return []

        response = payload.get("response")
        if not isinstance(response, dict):
            logger.warning("OKP MCP search result is missing response")
            return []
        docs = response.get("docs")
        if not isinstance(docs, list):
            logger.warning("OKP MCP search result is missing response.docs")
            return []
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

        citation = self._citation(doc)

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

    def _citation(self, doc: dict[str, Any]) -> str | None:
        """Return the citation URL for one Solr document.

        Args:
            doc: One entry from ``response.docs``.

        Returns:
            ``base_url`` joined with ``source_path`` when offline, otherwise
            ``online_source_url``. ``None`` when that field is missing or blank.

        """
        if self.offline:
            source_path = doc.get("source_path")
            if isinstance(source_path, str) and source_path:
                return f"{self.base_url.rstrip('/')}/{source_path.lstrip('/')}"
        else:
            online_source_url = doc.get("online_source_url")
            if isinstance(online_source_url, str) and online_source_url:
                return online_source_url
        return None

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
                message=f"OKP MCP server at {self.mcp_url} is unreachable: {detail}",
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
            async with streamable_http_client(
                self.mcp_url, http_client=http_client
            ) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session

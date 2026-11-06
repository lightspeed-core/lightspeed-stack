"""Unit tests for knowledge.sources.okp."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import httpx
import pytest
from mcp import McpError
from mcp.types import (
    CallToolResult,
    ContentBlock,
    ErrorData,
    ImageContent,
    ListToolsResult,
    TextContent,
    Tool,
)
from pytest_mock import MockerFixture, MockType

from knowledge.sources.okp import OkpKnowledgeSource, OkpProductFilter
from knowledge.types import KnowledgeMatch, KnowledgeReadiness

_URL = "https://host.example/mcp"
_LOGGER_NAME = "lightspeed_stack.knowledge.sources.okp"


def _source(**overrides: Any) -> OkpKnowledgeSource:
    """Build an OKP source with a stable name and endpoint.

    Args:
        overrides: Constructor fields that replace the defaults.

    Returns:
        A source pointed at ``_URL`` unless `overrides` sets ``url``.

    """
    values: dict[str, Any] = {"name": "okp", "url": _URL}
    values.update(overrides)
    return OkpKnowledgeSource(**values)


def _tool(name: str) -> Tool:
    """Build a minimal MCP tool definition.

    Args:
        name: Tool name.

    Returns:
        A tool with an empty object input schema.

    """
    return Tool(name=name, inputSchema={"type": "object"})


def _docs_result(
    docs: list[object],
    *,
    num_found: int | None = None,
) -> CallToolResult:
    """Build a successful search result from Solr-shaped documents.

    Args:
        docs: Values placed under ``response.docs``.
        num_found: Optional ``response.numFound`` value.

    Returns:
        A tool result whose structured content is a Solr response.

    """
    response: dict[str, Any] = {"docs": docs}
    if num_found is not None:
        response["numFound"] = num_found
    return CallToolResult(
        content=[],
        structuredContent={"response": response},
        isError=False,
    )


def _assert_closed(transport: _McpTransport) -> None:
    """Assert the HTTP client, transport, and session were closed once.

    Args:
        transport: Patched MCP stack for the test.

    """
    transport.http_cm.__aexit__.assert_awaited_once()
    transport.transport_cm.__aexit__.assert_awaited_once()
    transport.session_cm.__aexit__.assert_awaited_once()


@dataclass
class _McpTransport:
    """Doubles for the HTTP client, streamable transport, and MCP session."""

    http_cm: MockType
    client_constructor: MockType
    transport_cm: MockType
    transport: MockType
    session: MockType
    session_cm: MockType
    session_constructor: MockType


@pytest.fixture(name="mcp_transport")
def mcp_transport_fixture(mocker: MockerFixture) -> _McpTransport:
    """Patch the streamable HTTP stack used by an OKP source.

    Args:
        mocker: Pytest mocker.

    Returns:
        The patched client, transport, and session. ``list_tools`` reports a
        ``search`` tool and ``call_tool`` returns an empty document list.

    """
    http_cm: MockType = mocker.AsyncMock()
    http_cm.__aenter__.return_value = mocker.Mock(name="http_client")
    client_constructor = mocker.patch(
        "knowledge.sources.okp.httpx.AsyncClient",
        return_value=http_cm,
    )
    transport_cm: MockType = mocker.AsyncMock()
    transport_cm.__aenter__.return_value = ("read", "write", None)
    transport = mocker.patch(
        "knowledge.sources.okp.streamable_http_client",
        return_value=transport_cm,
    )
    session: MockType = mocker.AsyncMock()
    session.list_tools.return_value = ListToolsResult(tools=[_tool("search")])
    session.call_tool.return_value = _docs_result([])
    session_cm: MockType = mocker.AsyncMock()
    session_cm.__aenter__.return_value = session
    session_constructor = mocker.patch(
        "knowledge.sources.okp.ClientSession",
        return_value=session_cm,
    )
    return _McpTransport(
        http_cm=http_cm,
        client_constructor=client_constructor,
        transport_cm=transport_cm,
        transport=transport,
        session=session,
        session_cm=session_cm,
        session_constructor=session_constructor,
    )


class TestOkpProductFilter:
    """Tests for product restrictions passed to the OKP search tool."""

    def test_omits_versions_when_unset(self) -> None:
        """An empty version list is left out so the server matches every version."""
        assert OkpProductFilter("rhel").as_tool_argument() == {"product": "rhel"}

    def test_returns_versions_as_a_new_list(self) -> None:
        """Versions are copied into a list the caller can change."""
        product = OkpProductFilter("openshift_container_platform", ("4.19", "4.20"))

        argument = product.as_tool_argument()
        argument["versions"].append("4.21")

        assert argument == {
            "product": "openshift_container_platform",
            "versions": ["4.19", "4.20", "4.21"],
        }
        assert product.versions == ("4.19", "4.20")


class TestOkpKnowledgeSourceConfiguration:
    """Tests for source construction."""

    @pytest.mark.parametrize("rows", [0, 21, -1])
    def test_rejects_rows_outside_the_accepted_range(self, rows: int) -> None:
        """The search tool accepts 1 through 20 rows."""
        with pytest.raises(ValueError) as exc_info:
            _source(rows=rows)

        assert str(exc_info.value) == f"rows must be between 1 and 20, got {rows}"

    @pytest.mark.parametrize("rows", [1, 20])
    def test_accepts_boundary_row_counts(self, rows: int) -> None:
        """The inclusive row bounds are stored as given."""
        assert _source(rows=rows).rows == rows

    def test_defaults_are_independent_across_instances(self) -> None:
        """Each source gets its own header map and the documented defaults."""
        first = _source()
        second = _source()

        assert first.rows == 5
        assert first.offline is True
        assert isinstance(first.products, tuple)
        assert len(first.products) == 0
        assert isinstance(first.headers, dict)
        assert len(first.headers) == 0

        first.headers["X-Trace"] = "1"

        assert len(second.headers) == 0
        assert "X-Trace" not in second.headers


class TestOkpKnowledgeSourceSearch:
    """Tests for searching through the OKP MCP ``search`` tool."""

    @pytest.mark.asyncio
    async def test_maps_a_solr_document_to_a_knowledge_match(
        self,
        mcp_transport: _McpTransport,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Offline mode cites ``source_path`` and keeps the server score and order."""
        document = {
            "id": "solr-1",
            "doc_id": "doc-1",
            "chunk": "Install the operator.",
            "source_path": "/docs/install",
            "online_source_url": "https://docs.example/install",
            "title": "Install",
            "product": "openshift_container_platform",
            "product_version": "4.19",
            "category": "guide",
            "content_type": "assembly",
            "headings": ["Install"],
            "score": 1.5,
            "originalScore()": 0.25,
            "secret": "drop-me",
        }
        mcp_transport.session.call_tool.return_value = _docs_result(
            [document],
            num_found=42,
        )
        source = _source()

        with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
            matches = await source.search("How do I upgrade nodes?")

        assert matches == [
            KnowledgeMatch(
                content="Install the operator.",
                score=1.5,
                id="solr-1",
                source="/docs/install",
                metadata={
                    "category": "guide",
                    "content_type": "assembly",
                    "doc_id": "doc-1",
                    "headings": ["Install"],
                    "id": "solr-1",
                    "online_source_url": "https://docs.example/install",
                    "originalScore()": 0.25,
                    "product": "openshift_container_platform",
                    "product_version": "4.19",
                    "source_path": "/docs/install",
                    "title": "Install",
                },
            )
        ]
        mcp_transport.session.call_tool.assert_awaited_once_with(
            "search",
            arguments={"query": "How do I upgrade nodes?", "rows": 5},
            read_timeout_seconds=timedelta(seconds=60),
        )
        mcp_transport.session.list_tools.assert_not_awaited()
        assert "OKP MCP search numFound=42" in caplog.text
        assert "OKP MCP search returned 1 document(s)" in caplog.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("offline", "fields", "expected"),
        [
            (
                True,
                {
                    "source_path": "/offline",
                    "doc_id": "doc-1",
                    "online_source_url": "https://docs.example/on",
                },
                "/offline",
            ),
            (
                True,
                {
                    "source_path": "",
                    "doc_id": "doc-1",
                    "online_source_url": "https://docs.example/on",
                },
                None,
            ),
            (
                True,
                {
                    "online_source_url": "https://docs.example/on",
                },
                None,
            ),
            (
                False,
                {
                    "online_source_url": "https://docs.example/on",
                    "source_path": "/offline",
                    "doc_id": "doc-1",
                },
                "https://docs.example/on",
            ),
            (
                False,
                {
                    "online_source_url": "",
                    "source_path": "/offline",
                    "doc_id": "doc-1",
                },
                "/offline",
            ),
            (False, {}, None),
        ],
        ids=[
            "offline-uses-source-path",
            "offline-skips-blank-source-path",
            "offline-ignores-online-url",
            "online-prefers-url",
            "online-falls-back-to-source-path",
            "online-without-citation",
        ],
    )
    async def test_chooses_citation_from_offline_or_online_fields(
        self,
        mcp_transport: _McpTransport,
        offline: bool,
        fields: dict[str, Any],
        expected: str | None,
    ) -> None:
        """Offline cites ``source_path``. Online cites the URL, then ``source_path``."""
        mcp_transport.session.call_tool.return_value = _docs_result(
            [{"chunk": "Install the operator.", "id": "solr-1", "score": 1, **fields}]
        )

        matches = await _source(offline=offline).search("install")

        match = matches[0]
        assert match.source == expected
        if "doc_id" in fields:
            assert match.metadata["doc_id"] == fields["doc_id"]
        else:
            assert "doc_id" not in match.metadata

    @pytest.mark.asyncio
    async def test_metadata_keeps_known_fields_and_drops_unknown_ones(
        self, mcp_transport: _McpTransport
    ) -> None:
        """Only populated allowlisted fields are copied onto the match."""
        mcp_transport.session.call_tool.return_value = _docs_result(
            [
                {
                    "chunk": "Install the operator.",
                    "id": "solr-1",
                    "score": 1,
                    "title": None,
                    "product": "rhel",
                    "headings": [],
                    "originalScore()": False,
                    "secret": "drop-me",
                }
            ]
        )

        matches = await _source().search("install")

        assert matches[0].metadata == {
            "headings": [],
            "id": "solr-1",
            "originalScore()": False,
            "product": "rhel",
        }
        assert matches[0].source is None

    @pytest.mark.asyncio
    async def test_uses_the_document_score(self, mcp_transport: _McpTransport) -> None:
        """The Solr score is stored as a float."""
        mcp_transport.session.call_tool.return_value = _docs_result(
            [{"id": "numeric", "chunk": "a", "score": 2}]
        )

        matches = await _source().search("scores")

        assert matches[0].score == 2.0
        assert isinstance(matches[0].score, float)

    @pytest.mark.asyncio
    async def test_match_id_is_the_document_id(
        self, mcp_transport: _McpTransport
    ) -> None:
        """The Solr ``id`` is stored as a string and is not replaced by ``doc_id``."""
        mcp_transport.session.call_tool.return_value = _docs_result(
            [
                {"chunk": "a", "id": "solr-1", "doc_id": "doc-1", "score": 1},
                {"chunk": "b", "id": 7, "doc_id": "doc-3", "score": 1},
            ]
        )

        matches = await _source().search("ids")

        assert [match.id for match in matches] == ["solr-1", "7"]
        assert matches[0].source is None
        assert matches[0].metadata["doc_id"] == "doc-1"
        assert matches[1].metadata["doc_id"] == "doc-3"

    @pytest.mark.asyncio
    async def test_returns_at_most_rows_chunks_that_have_text(
        self,
        mcp_transport: _McpTransport,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Blank chunks and non-documents are skipped before the row limit."""
        mcp_transport.session.call_tool.return_value = _docs_result(
            [
                "not-a-document",
                {"chunk": " \n", "id": "blank"},
                {"chunk": "  kept  ", "id": "kept", "score": 1},
                {"chunk": "second", "id": "second", "score": 2},
                {"chunk": "third", "id": "third", "score": 3},
            ],
            num_found=9,
        )

        with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
            matches = await _source(rows=2).search("limit")

        assert matches == [
            KnowledgeMatch(
                content="  kept  ",
                score=1.0,
                id="kept",
                source=None,
                metadata={"id": "kept"},
            ),
            KnowledgeMatch(
                content="second",
                score=2.0,
                id="second",
                source=None,
                metadata={"id": "second"},
            ),
        ]
        assert (
            mcp_transport.session.call_tool.await_args.kwargs["arguments"]["rows"] == 2
        )
        assert "OKP MCP search numFound=9" in caplog.text
        assert "OKP MCP search returned 2 document(s)" in caplog.text

    @pytest.mark.asyncio
    async def test_returns_an_empty_list_when_no_document_has_text(
        self,
        mcp_transport: _McpTransport,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A response whose documents have no chunk text is an empty match list."""
        mcp_transport.session.call_tool.return_value = _docs_result(
            [
                None,
                "not-a-document",
                {"chunk": " \n\t", "id": "blank"},
                {"chunk": 5, "id": "number"},
                {"id": "missing"},
            ],
            num_found=4,
        )

        with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
            matches = await _source().search("empty")

        assert matches == []
        assert "OKP MCP search numFound=4" in caplog.text
        assert "OKP MCP search returned 0 document(s)" in caplog.text

    @pytest.mark.asyncio
    async def test_sends_product_filters_with_the_query(
        self, mcp_transport: _McpTransport
    ) -> None:
        """Product filters are OR-combined as tool arguments and versions are lists."""
        products = (
            OkpProductFilter("openshift_container_platform", ("4.19", "4.20")),
            OkpProductFilter("rhel"),
        )
        source = _source(rows=3, products=products)

        matches = await source.search("upgrade")

        assert matches == []
        mcp_transport.session.call_tool.assert_awaited_once_with(
            "search",
            arguments={
                "query": "upgrade",
                "rows": 3,
                "products": [
                    {
                        "product": "openshift_container_platform",
                        "versions": ["4.19", "4.20"],
                    },
                    {"product": "rhel"},
                ],
            },
            read_timeout_seconds=timedelta(seconds=60),
        )
        assert source.products == products

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("content", "message"),
        [
            (
                [
                    TextContent(type="text", text="index unavailable"),
                    ImageContent(type="image", data="aaaa", mimeType="image/png"),
                    TextContent(type="text", text=""),
                    TextContent(type="text", text="retry later"),
                ],
                "index unavailable; retry later",
            ),
            (
                [ImageContent(type="image", data="aaaa", mimeType="image/png")],
                "OKP MCP search failed",
            ),
            ([], "OKP MCP search failed"),
        ],
        ids=["text-blocks", "non-text-block", "no-content"],
    )
    async def test_raises_when_the_tool_result_is_an_error(
        self,
        mcp_transport: _McpTransport,
        caplog: pytest.LogCaptureFixture,
        content: Sequence[ContentBlock],
        message: str,
    ) -> None:
        """An error result raises the tool text and does not return documents."""
        mcp_transport.session.call_tool.return_value = CallToolResult(
            content=list(content),
            structuredContent={
                "response": {"docs": [{"chunk": "hidden", "id": "hidden"}]}
            },
            isError=True,
        )

        with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
            with pytest.raises(RuntimeError) as exc_info:
                await _source().search("upgrade")

        assert str(exc_info.value) == message
        assert "OKP MCP search returned" not in caplog.text
        assert "numFound" not in caplog.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("payload", "message"),
        [
            (None, "OKP MCP search returned no structured result"),
            ({"foo": 1}, "OKP MCP search result is missing response"),
            ({"response": []}, "OKP MCP search result is missing response"),
            (
                {"response": {"docs": {}}},
                "OKP MCP search result is missing response.docs",
            ),
        ],
        ids=["no-payload", "no-response", "response-not-object", "docs-not-a-list"],
    )
    async def test_raises_when_the_result_has_no_document_list(
        self,
        mcp_transport: _McpTransport,
        caplog: pytest.LogCaptureFixture,
        payload: dict[str, Any] | None,
        message: str,
    ) -> None:
        """A result without ``response.docs`` is a failed search."""
        mcp_transport.session.call_tool.return_value = CallToolResult(
            content=[],
            structuredContent=payload,
        )

        with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
            with pytest.raises(RuntimeError) as exc_info:
                await _source().search("upgrade")

        assert str(exc_info.value) == message
        assert "numFound" not in caplog.text

    @pytest.mark.asyncio
    async def test_reads_documents_from_text_when_structured_content_is_absent(
        self,
        mcp_transport: _McpTransport,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """JSON text is parsed after blank, invalid, and non-object blocks."""
        payload = {
            "response": {
                "numFound": 7,
                "docs": [
                    {
                        "chunk": "from text",
                        "id": "text-1",
                        "score": 1.25,
                        "source_path": "/docs/text",
                    }
                ],
            }
        }
        mcp_transport.session.call_tool.return_value = CallToolResult(
            content=[
                ImageContent(type="image", data="aaaa", mimeType="image/png"),
                TextContent(type="text", text="   "),
                TextContent(type="text", text="not-json"),
                TextContent(type="text", text="[1, 2]"),
                TextContent(type="text", text="null"),
                TextContent(type="text", text=json.dumps(payload)),
            ],
            structuredContent=None,
        )

        with caplog.at_level(logging.DEBUG, logger=_LOGGER_NAME):
            matches = await _source().search("from text")

        assert matches == [
            KnowledgeMatch(
                content="from text",
                score=1.25,
                id="text-1",
                source="/docs/text",
                metadata={"id": "text-1", "source_path": "/docs/text"},
            )
        ]
        assert "OKP MCP search numFound=7" in caplog.text

    @pytest.mark.asyncio
    async def test_prefers_structured_content_over_text(
        self, mcp_transport: _McpTransport
    ) -> None:
        """A structured document list is used even when text carries another one."""
        text_payload = {
            "response": {"docs": [{"chunk": "from text", "id": "text-1", "score": 1}]}
        }
        mcp_transport.session.call_tool.return_value = CallToolResult(
            content=[TextContent(type="text", text=json.dumps(text_payload))],
            structuredContent={
                "response": {
                    "docs": [{"chunk": "from structured", "id": "struct-1", "score": 1}]
                }
            },
        )

        matches = await _source().search("prefer structured")

        assert [(match.id, match.content) for match in matches] == [
            ("struct-1", "from structured")
        ]

    @pytest.mark.asyncio
    async def test_propagates_connection_errors(
        self, mcp_transport: _McpTransport
    ) -> None:
        """Transport failures from a tool call are not turned into match results."""
        mcp_transport.session.call_tool.side_effect = httpx.ConnectError("reset")

        with pytest.raises(httpx.ConnectError) as exc_info:
            await _source().search("upgrade")

        assert str(exc_info.value) == "reset"
        _assert_closed(mcp_transport)


class TestOkpKnowledgeSourceReadiness:
    """Tests for the MCP readiness probe."""

    @pytest.mark.asyncio
    async def test_reports_ready_when_search_is_listed(
        self, mcp_transport: _McpTransport
    ) -> None:
        """Ready means the server lists ``search``, alongside any other tools."""
        mcp_transport.session.list_tools.return_value = ListToolsResult(
            tools=[_tool("other"), _tool("search")]
        )

        result = await _source().readiness()

        assert result == KnowledgeReadiness(
            status="ready",
            message="OKP MCP search tool is available",
        )
        mcp_transport.session.call_tool.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tool_names",
        [[], ["other"]],
        ids=["no-tools", "other-tool-only"],
    )
    async def test_reports_not_ready_when_search_is_missing(
        self,
        mcp_transport: _McpTransport,
        tool_names: list[str],
    ) -> None:
        """A reachable server without ``search`` is not ready."""
        mcp_transport.session.list_tools.return_value = ListToolsResult(
            tools=[_tool(name) for name in tool_names]
        )

        result = await _source().readiness()

        assert result == KnowledgeReadiness(
            status="not_ready",
            message="OKP MCP server does not expose the 'search' tool",
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("error", "detail"),
        [
            (httpx.ConnectError("connection refused"), "connection refused"),
            (
                McpError(ErrorData(code=-32000, message="session expired")),
                "session expired",
            ),
            (
                ExceptionGroup(
                    "outer",
                    [
                        ExceptionGroup(
                            "inner",
                            [
                                httpx.ConnectError("down"),
                                httpx.ConnectError("ignored"),
                            ],
                        )
                    ],
                ),
                "down",
            ),
        ],
        ids=["http-error", "mcp-error", "grouped-error"],
    )
    async def test_reports_not_ready_when_the_server_is_unreachable(
        self,
        mcp_transport: _McpTransport,
        error: BaseException,
        detail: str,
    ) -> None:
        """Connection failures report the first nested error and the source URL."""
        mcp_transport.session.list_tools.side_effect = error
        url = "https://okp.example/mcp"

        result = await _source(url=url).readiness()

        assert result == KnowledgeReadiness(
            status="not_ready",
            message=f"OKP MCP server at {url} is unreachable: {detail}",
        )
        _assert_closed(mcp_transport)

    @pytest.mark.asyncio
    async def test_propagates_unexpected_errors(
        self, mcp_transport: _McpTransport
    ) -> None:
        """Errors that are not connection failures still close the session."""
        mcp_transport.session.list_tools.side_effect = ValueError("boom")

        with pytest.raises(ValueError) as exc_info:
            await _source().readiness()

        assert str(exc_info.value) == "boom"
        _assert_closed(mcp_transport)


class TestOkpKnowledgeSourceConnection:
    """Tests for the streamable HTTP session opened on each call."""

    @pytest.mark.asyncio
    async def test_opens_an_initialized_session_and_closes_it(
        self, mcp_transport: _McpTransport
    ) -> None:
        """The session is initialized before use and every connection is closed."""
        url = "https://okp.example/mcp"

        async def _list_tools() -> ListToolsResult:
            """Return tools while the connection is still open."""
            mcp_transport.session.initialize.assert_awaited_once()
            mcp_transport.http_cm.__aexit__.assert_not_awaited()
            mcp_transport.transport_cm.__aexit__.assert_not_awaited()
            mcp_transport.session_cm.__aexit__.assert_not_awaited()
            return ListToolsResult(tools=[_tool("search")])

        mcp_transport.session.list_tools.side_effect = _list_tools

        result = await _source(url=url).readiness()

        assert result.status == "ready"
        kwargs = mcp_transport.client_constructor.call_args.kwargs
        assert kwargs["timeout"] == httpx.Timeout(30.0, read=60.0)
        assert kwargs["follow_redirects"] is True
        mcp_transport.transport.assert_called_once_with(
            url,
            http_client=mcp_transport.http_cm.__aenter__.return_value,
        )
        mcp_transport.session_constructor.assert_called_once_with("read", "write")
        _assert_closed(mcp_transport)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("headers", "expected"),
        [
            (
                {"Authorization": "raw-token", "X-Trace": "abc"},
                {"Authorization": "Bearer raw-token", "X-Trace": "abc"},
            ),
            (
                {"Authorization": "Bearer raw-token"},
                {"Authorization": "Bearer raw-token"},
            ),
            (
                {"authorization": "raw-token"},
                {"authorization": "Bearer raw-token"},
            ),
            (
                {"Authorization": "bearer token"},
                {"Authorization": "Bearer bearer token"},
            ),
            ({"Authorization": ""}, {"Authorization": ""}),
            ({}, {}),
        ],
        ids=[
            "raw-token",
            "already-prefixed",
            "lowercase-header-name",
            "lowercase-scheme",
            "empty-authorization",
            "no-headers",
        ],
    )
    async def test_prefixes_the_authorization_header(
        self,
        mcp_transport: _McpTransport,
        headers: dict[str, str],
        expected: dict[str, str],
    ) -> None:
        """Authorization is sent as Bearer and the source headers stay unchanged."""
        source = _source(headers=dict(headers))

        result = await source.readiness()

        assert result.status == "ready"
        assert source.headers == headers
        assert mcp_transport.client_constructor.call_args.kwargs["headers"] == expected

    @pytest.mark.asyncio
    async def test_opens_a_new_session_for_every_call(
        self, mcp_transport: _McpTransport
    ) -> None:
        """Sequential searches do not reuse one MCP session."""
        source = _source()

        await source.search("one")
        await source.search("two")

        assert mcp_transport.client_constructor.call_count == 2
        assert mcp_transport.transport.call_count == 2
        assert mcp_transport.session_constructor.call_count == 2
        assert mcp_transport.session.initialize.await_count == 2
        assert mcp_transport.session.call_tool.await_count == 2
        assert mcp_transport.http_cm.__aexit__.await_count == 2
        queries = [
            call.kwargs["arguments"]["query"]
            for call in mcp_transport.session.call_tool.await_args_list
        ]
        assert queries == ["one", "two"]

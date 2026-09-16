"""Unit tests for the OKP MCP client wrapper."""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pydantic_ai_lightspeed.retrieval.okp_mcp import _client


@pytest.mark.asyncio
async def test_call_okp_search_returns_structured_mapping(
    mocker: MockerFixture,
) -> None:
    """A mapping result from the tool is returned as a plain dict."""
    payload = {"response": {"numFound": 1, "docs": [{"chunk": "x"}]}}
    toolset = mocker.Mock()
    toolset.direct_call_tool = mocker.AsyncMock(return_value=payload)
    toolset_cls = mocker.patch.object(_client, "MCPToolset", return_value=toolset)

    result = await _client.call_okp_search(
        url="http://okp/mcp", tool_name="search", query="q", rows=5
    )

    assert result == payload
    # URL is the positional client arg; error behavior is strict.
    args, kwargs = toolset_cls.call_args
    assert args[0] == "http://okp/mcp"
    assert kwargs["tool_error_behavior"] == "error"
    toolset.direct_call_tool.assert_awaited_once_with(
        "search", {"query": "q", "rows": 5}
    )


@pytest.mark.asyncio
async def test_call_okp_search_forwards_headers_and_timeout(
    mocker: MockerFixture,
) -> None:
    """Headers and timeout are forwarded to the toolset when provided."""
    toolset = mocker.Mock()
    toolset.direct_call_tool = mocker.AsyncMock(return_value={})
    toolset_cls = mocker.patch.object(_client, "MCPToolset", return_value=toolset)

    await _client.call_okp_search(
        url="http://okp/mcp",
        tool_name="search",
        query="q",
        rows=3,
        headers={"Authorization": "Bearer t"},
        timeout=12.0,
    )

    _, kwargs = toolset_cls.call_args
    assert kwargs["headers"] == {"Authorization": "Bearer t"}
    assert kwargs["init_timeout"] == 12.0
    assert kwargs["read_timeout"] == 12.0


@pytest.mark.asyncio
async def test_call_okp_search_omits_product_filters_when_none(
    mocker: MockerFixture,
) -> None:
    """Product filters are absent from the tool args when not supplied."""
    toolset = mocker.Mock()
    toolset.direct_call_tool = mocker.AsyncMock(return_value={})
    mocker.patch.object(_client, "MCPToolset", return_value=toolset)

    await _client.call_okp_search(
        url="http://okp/mcp", tool_name="search", query="q", rows=5
    )

    toolset.direct_call_tool.assert_awaited_once_with(
        "search", {"query": "q", "rows": 5}
    )


@pytest.mark.asyncio
async def test_call_okp_search_forwards_product_filters(
    mocker: MockerFixture,
) -> None:
    """Product and product_version are added to the tool args when supplied."""
    toolset = mocker.Mock()
    toolset.direct_call_tool = mocker.AsyncMock(return_value={})
    mocker.patch.object(_client, "MCPToolset", return_value=toolset)

    await _client.call_okp_search(
        url="http://okp/mcp",
        tool_name="search",
        query="q",
        rows=5,
        product="openshift_container_platform",
        product_version="4.20",
    )

    toolset.direct_call_tool.assert_awaited_once_with(
        "search",
        {
            "query": "q",
            "rows": 5,
            "product": "openshift_container_platform",
            "product_version": "4.20",
        },
    )


@pytest.mark.asyncio
async def test_call_okp_search_non_mapping_result_returns_empty(
    mocker: MockerFixture,
) -> None:
    """A non-mapping tool result is ignored and an empty dict is returned."""
    toolset = mocker.Mock()
    toolset.direct_call_tool = mocker.AsyncMock(return_value="just text")
    mocker.patch.object(_client, "MCPToolset", return_value=toolset)

    result: dict[str, Any] = await _client.call_okp_search(
        url="http://okp/mcp", tool_name="search", query="q", rows=5
    )

    assert result == {}


@pytest.mark.asyncio
async def test_probe_okp_mcp_true_when_tool_advertised(
    mocker: MockerFixture,
) -> None:
    """The probe returns True when the endpoint advertises the search tool."""
    tool = mocker.Mock()
    tool.name = "search"
    toolset = mocker.Mock()
    toolset.list_tools = mocker.AsyncMock(return_value=[tool])
    mocker.patch.object(_client, "MCPToolset", return_value=toolset)

    assert await _client.probe_okp_mcp("http://okp/mcp", "search") is True


@pytest.mark.asyncio
async def test_probe_okp_mcp_false_when_tool_absent(
    mocker: MockerFixture,
) -> None:
    """The probe returns False when the search tool is not advertised."""
    tool = mocker.Mock()
    tool.name = "other"
    toolset = mocker.Mock()
    toolset.list_tools = mocker.AsyncMock(return_value=[tool])
    mocker.patch.object(_client, "MCPToolset", return_value=toolset)

    assert await _client.probe_okp_mcp("http://okp/mcp", "search") is False


@pytest.mark.asyncio
async def test_probe_okp_mcp_false_on_transport_error(
    mocker: MockerFixture,
) -> None:
    """The probe never raises: a transport error degrades to False."""
    toolset = mocker.Mock()
    toolset.list_tools = mocker.AsyncMock(side_effect=RuntimeError("no route"))
    mocker.patch.object(_client, "MCPToolset", return_value=toolset)

    assert await _client.probe_okp_mcp("http://okp/mcp", "search") is False


@pytest.mark.asyncio
async def test_probe_okp_mcp_forwards_headers_and_timeout(
    mocker: MockerFixture,
) -> None:
    """Headers and timeout are forwarded to the toolset when provided."""
    toolset = mocker.Mock()
    toolset.list_tools = mocker.AsyncMock(return_value=[])
    toolset_cls = mocker.patch.object(_client, "MCPToolset", return_value=toolset)

    await _client.probe_okp_mcp(
        "http://okp/mcp",
        "search",
        headers={"Authorization": "Bearer t"},
        timeout=5.0,
    )

    _, kwargs = toolset_cls.call_args
    assert kwargs["headers"] == {"Authorization": "Bearer t"}
    assert kwargs["init_timeout"] == 5.0
    assert kwargs["read_timeout"] == 5.0

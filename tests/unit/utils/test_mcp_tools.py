"""Unit tests for MCP tool discovery utilities."""

import httpx
import pytest
from pytest_mock import MockerFixture

from utils.mcp_tools import _MCP_HTTP_TIMEOUT, list_mcp_tools


@pytest.mark.asyncio
async def test_list_mcp_tools_forwards_headers_to_transport(
    mocker: MockerFixture,
) -> None:
    """Forward headers to the MCP HTTP client, adding Bearer when missing."""
    mock_http_client = mocker.AsyncMock()
    mock_http_client.__aenter__ = mocker.AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = mocker.AsyncMock(return_value=None)

    mock_async_client = mocker.patch(
        "utils.mcp_tools.httpx.AsyncClient",
        return_value=mock_http_client,
    )
    mock_streamable = mocker.patch("utils.mcp_tools.streamable_http_client")
    mock_streamable.return_value.__aenter__ = mocker.AsyncMock(
        return_value=(mocker.Mock(), mocker.Mock(), mocker.Mock())
    )
    mock_streamable.return_value.__aexit__ = mocker.AsyncMock(return_value=None)
    mocker.patch(
        "utils.mcp_tools._list_tools_from_session",
        new=mocker.AsyncMock(return_value=[]),
    )

    await list_mcp_tools(
        "http://localhost:3000/mcp",
        headers={
            "Authorization": "client-token",
            "X-Custom": "value",
        },
    )

    mock_async_client.assert_called_once_with(
        headers={
            "Authorization": "Bearer client-token",
            "X-Custom": "value",
        },
        timeout=_MCP_HTTP_TIMEOUT,
        follow_redirects=True,
    )


@pytest.mark.asyncio
async def test_list_mcp_tools_returns_empty_list_when_all_transports_fail(
    mocker: MockerFixture,
) -> None:
    """Skip unavailable MCP servers by returning an empty tool list."""
    mocker.patch(
        "utils.mcp_tools._MCP_TRANSPORTS",
        (
            (
                "streamable HTTP",
                mocker.AsyncMock(side_effect=httpx.ConnectError("boom")),
            ),
            ("SSE", mocker.AsyncMock(side_effect=httpx.TimeoutException("timeout"))),
        ),
    )

    tools = await list_mcp_tools("http://localhost:3000/mcp", headers={})

    assert tools == []


@pytest.mark.asyncio
async def test_list_mcp_tools_returns_empty_list_on_http_error(
    mocker: MockerFixture,
) -> None:
    """Skip MCP servers that return HTTP errors."""
    request = httpx.Request("GET", "http://localhost:3000/mcp")
    response = httpx.Response(401, request=request)
    http_error = httpx.HTTPStatusError(
        "HTTP 401",
        request=request,
        response=response,
    )
    mocker.patch(
        "utils.mcp_tools._MCP_TRANSPORTS",
        (
            ("streamable HTTP", mocker.AsyncMock(side_effect=http_error)),
            ("SSE", mocker.AsyncMock(side_effect=http_error)),
        ),
    )

    tools = await list_mcp_tools("http://localhost:3000/mcp", headers={})

    assert tools == []

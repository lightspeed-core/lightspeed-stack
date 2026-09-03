"""Utilities for discovering tools from remote MCP servers without Llama Stack."""

from __future__ import annotations

from typing import Any, Optional

import httpx
from mcp import ClientSession, McpError
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

from log import get_logger
from models.common.tools import ListedMcpTool

logger = get_logger(__name__)


# Match MCP SDK defaults previously provided by create_mcp_http_client.
_MCP_HTTP_TIMEOUT = httpx.Timeout(30.0, read=300.0)

_TRANSPORT_ERRORS = (
    httpx.HTTPStatusError,
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.RequestError,
    McpError,
)

# Streamable HTTP wraps transport failures in ExceptionGroup (BaseException subclass).
_LIST_MCP_ERRORS = (*_TRANSPORT_ERRORS, ExceptionGroup)


def _transport_failure(exc: BaseException) -> Optional[BaseException]:
    """Return a transport failure if ``exc`` (or a nested ExceptionGroup) is one."""
    if isinstance(exc, _TRANSPORT_ERRORS):
        return exc
    if isinstance(exc, ExceptionGroup):
        for nested in exc.exceptions:
            found = _transport_failure(nested)
            if found is not None:
                return found
    return None


async def _list_tools_from_session(
    read_stream: Any,
    write_stream: Any,
) -> list[ListedMcpTool]:
    """Run ``tools/list`` on an initialized MCP client session."""
    async with ClientSession(
        read_stream=read_stream,
        write_stream=write_stream,
    ) as session:
        await session.initialize()
        tools_result = await session.list_tools()
        return [
            ListedMcpTool(
                name=tool.name,
                description=tool.description,
                input_schema=tool.inputSchema,
            )
            for tool in tools_result.tools
        ]


async def _list_via_streamable_http(
    endpoint: str,
    headers: dict[str, str],
) -> list[ListedMcpTool]:
    """List tools using the streamable HTTP MCP transport."""
    async with httpx.AsyncClient(
        headers=headers,
        timeout=_MCP_HTTP_TIMEOUT,
        follow_redirects=True,
    ) as http_client:
        async with streamable_http_client(
            endpoint,
            http_client=http_client,
        ) as (read_stream, write_stream, _):
            return await _list_tools_from_session(read_stream, write_stream)


async def _list_via_sse(
    endpoint: str,
    headers: dict[str, str],
) -> list[ListedMcpTool]:
    """List tools using the SSE MCP transport."""
    async with sse_client(endpoint, headers=headers) as (read_stream, write_stream):
        return await _list_tools_from_session(read_stream, write_stream)


# Prefer streamable HTTP; fall back to SSE for servers that only support it.
_MCP_TRANSPORTS = (
    ("streamable HTTP", _list_via_streamable_http),
    ("SSE", _list_via_sse),
)


def _prepare_mcp_request_headers(headers: dict[str, str]) -> dict[str, str]:
    """Normalize headers for a direct MCP HTTP call.

    File-based secrets are stored as raw tokens. MCP servers expect
    ``Authorization: Bearer <token>``. Query/Responses keep the raw value in
    ``build_mcp_headers`` and hand it to Llama Stack separately; only this
    direct client path needs the Bearer scheme.
    """
    prepared = dict(headers)
    for header_name, value in list(prepared.items()):
        if (
            header_name.lower() == "authorization"
            and value
            and not value.startswith("Bearer ")
        ):
            prepared[header_name] = f"Bearer {value}"
    return prepared


async def list_mcp_tools(
    endpoint: str,
    headers: dict[str, str],
) -> list[ListedMcpTool]:
    """List tools exposed by a remote MCP server.

    Tries streamable HTTP first, then SSE. Discovery failures are logged and
    result in an empty list so callers can skip unavailable servers.

    Parameters:
        endpoint: MCP server URL.
        headers: Headers to forward (already resolved by the caller).

    Returns:
        Tool definitions discovered from the MCP server, or an empty list when
        the server is unavailable or returns an error.
    """
    request_headers = _prepare_mcp_request_headers(headers)
    for index, (transport_name, list_via) in enumerate(_MCP_TRANSPORTS):
        try:
            return await list_via(endpoint, request_headers)
        except _LIST_MCP_ERRORS as exc:
            transport_exc = _transport_failure(exc)
            if transport_exc is None:
                raise
            if index < len(_MCP_TRANSPORTS) - 1:
                logger.warning(
                    "Failed to list tools from %s via %s, trying next transport: %s",
                    endpoint,
                    transport_name,
                    transport_exc,
                )
                continue
            logger.warning(
                "Skipping MCP server at %s: unable to list tools via any transport: %s",
                endpoint,
                transport_exc,
            )

    return []

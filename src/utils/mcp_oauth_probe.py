"""Probe MCP servers for OAuth and raise 401 with WWW-Authenticate when required.

Used by endpoints that call MCP-backed services so clients receive a proper
401 with WWW-Authenticate when an MCP server requires OAuth.
"""

import asyncio
from collections.abc import Mapping
from typing import Optional

import aiohttp
from fastapi import HTTPException

import constants
from configuration import AppConfig
from log import get_logger
from models.responses import UnauthorizedResponse
from utils.mcp_headers import McpHeaders, build_mcp_headers

logger = get_logger(__name__)


async def check_mcp_auth(
    configuration: AppConfig,
    mcp_headers: McpHeaders,
    token: str,
    request_headers: Optional[Mapping[str, str]] = None,
) -> None:
    """Probe each configured MCP server that expects authentication.

    Builds complete MCP headers by merging client-provided headers with
    resolved authorization headers (file-based, kubernetes, oauth, or client).
    For every MCP server that has an Authorization header or has authentication
    configured, performs a probe request. If the server indicates authentication
    failure, raises 401 with WWW-Authenticate (or 401 without header on probe failure).

    Parameters:
    ----------
        configuration: Application config containing mcp_servers.
        mcp_headers: Per-server headers from client; keys are MCP server names.
        token: Authentication token from the request (used for kubernetes auth).
        request_headers: Headers from the incoming HTTP request for propagation.

    Returns:
    -------
        None when no server requires authentication or probe does not trigger 401.

    Raises:
    ------
        HTTPException: 401 when an MCP server requires authentication (from probe_mcp).
    """
    complete_headers = build_mcp_headers(
        configuration, mcp_headers or {}, request_headers, token
    )

    probes = []
    for mcp_server in configuration.mcp_servers:
        headers = complete_headers.get(mcp_server.name, {})
        auth_header = headers.get("Authorization")
        if auth_header is not None:
            authorization = (
                auth_header
                if auth_header.startswith("Bearer ")
                else f"Bearer {auth_header}"
            )
        else:
            authorization = None

        if (
            authorization
            or constants.MCP_AUTH_OAUTH
            in mcp_server.resolved_authorization_headers.values()
        ):
            probes.append(probe_mcp(mcp_server.url, authorization=authorization))
    if probes:
        await asyncio.gather(*probes)


async def probe_mcp(
    url: str,
    authorization: Optional[str] = None,
) -> None:
    """Probe MCP endpoint and raise 401 so the client can perform OAuth.

    Performs an async GET to the given URL. If the response is 401 with
    WWW-Authenticate, raises HTTPException with that header. If the response
    is 401 without the header, or the probe fails (connection error, timeout),
    raises 401 without WWW-Authenticate.

    Parameters:
    ----------
        url: MCP server URL to probe.
        authorization: Optional Authorization header value for the probe request.

    Returns:
    -------
        None when the server responds with a status other than 401 (OAuth not
        required). Otherwise does not return; raises HTTPException.

    Raises:
    ------
        HTTPException: 401 with WWW-Authenticate when the server returns 401
            and includes that header; 401 without the header when the server
            returns 401 without it or when the probe fails (timeout/connection).
    """
    cause = f"MCP server at {url} requires OAuth"
    error_response = UnauthorizedResponse(cause=cause)
    headers: Optional[dict[str, str]] = (
        {"authorization": authorization} if authorization is not None else None
    )
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 401:
                    return
                www_auth = resp.headers.get("WWW-Authenticate")
                if www_auth is None:
                    logger.warning("No WWW-Authenticate header received from %s", url)
                    raise HTTPException(**error_response.model_dump())
                raise HTTPException(
                    **error_response.model_dump(),
                    headers={"WWW-Authenticate": www_auth},
                )
    except (aiohttp.ClientError, TimeoutError) as probe_err:
        logger.warning("OAuth probe failed for %s: %s", url, probe_err)
        raise HTTPException(**error_response.model_dump()) from probe_err

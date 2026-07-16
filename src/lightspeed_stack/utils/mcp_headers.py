"""MCP headers handling."""

import json
from collections.abc import Mapping
from typing import Optional
from urllib.parse import urlparse

from fastapi import Request

import constants
from configuration import AppConfig
from log import get_logger
from models.config import ModelContextProtocolServer

logger = get_logger(__name__)

type McpHeaders = dict[str, dict[str, str]]


async def mcp_headers_dependency(request: Request) -> McpHeaders:
    """Get the MCP headers dependency to passed to mcp servers.

    mcp headers is a json dictionary or mcp url paths and their respective headers

    Parameters:
    ----------
        request (Request): The FastAPI request object.

    Returns:
    -------
        The mcp headers dictionary, or empty dictionary if not found or on json decoding error
    """
    return extract_mcp_headers(request)


def extract_mcp_headers(request: Request) -> McpHeaders:
    """Extract mcp headers from MCP-HEADERS header.

    If the header is missing, contains invalid JSON, or the decoded
    value is not a dictionary, an empty dictionary is returned.

    Parameters:
    ----------
        request: The FastAPI request object

    Returns:
    -------
        The mcp headers dictionary, or empty dictionary if not found or on json decoding error
    """
    mcp_headers_string = request.headers.get("MCP-HEADERS", "")
    mcp_headers = {}
    if mcp_headers_string:
        try:
            mcp_headers = json.loads(mcp_headers_string)
        except json.decoder.JSONDecodeError as e:
            logger.error("MCP headers decode error: %s", e)

        if not isinstance(mcp_headers, dict):
            logger.error(
                "MCP headers wrong type supplied (mcp headers must be a dictionary), "
                "but type %s was supplied",
                type(mcp_headers),
            )
            mcp_headers = {}
    return mcp_headers


def handle_mcp_headers_with_toolgroups(
    mcp_headers: McpHeaders, config: AppConfig
) -> McpHeaders:
    """Process MCP headers by converting toolgroup names to URLs.

    This function takes MCP headers where keys can be either valid URLs or
    toolgroup names. For valid URLs (HTTP/HTTPS), it keeps them as-is. For
    toolgroup names, it looks up the corresponding MCP server URL in the
    configuration and replaces the key with the URL. Unknown toolgroup names
    are filtered out.

    Args:
        mcp_headers: Dictionary with keys as URLs or toolgroup names
        config: Application configuration containing MCP server definitions

    Returns:
        Dictionary with URLs as keys and their corresponding headers as values
    """
    converted_mcp_headers = {}

    for key, item in mcp_headers.items():
        key_url_parsed = urlparse(key)
        if key_url_parsed.scheme in ("http", "https") and key_url_parsed.netloc:
            # a valid url is supplied, deliver it as is
            converted_mcp_headers[key] = item
        else:
            # assume the key is a toolgroup name
            # look for toolgroups name in mcp_servers configuration
            # if the mcp server is not found, the mcp header gets ignored
            for mcp_server in config.mcp_servers:
                if mcp_server.name == key and mcp_server.url:
                    converted_mcp_headers[mcp_server.url] = item
                    break

    return converted_mcp_headers


def extract_propagated_headers(
    mcp_server: ModelContextProtocolServer,
    request_headers: Mapping[str, str],
) -> dict[str, str]:
    """Extract headers from the incoming request based on the server's allowlist.

    For each header name in the MCP server's ``headers`` allowlist, looks up
    the corresponding value in the incoming request headers (case-insensitive)
    and returns the matches.

    Args:
        mcp_server: MCP server configuration containing the headers allowlist.
        request_headers: Headers from the incoming HTTP request.

    Returns:
        Dictionary of header names to values extracted from the request.
        Only headers present in both the allowlist and the request are included.
    """
    lower_request_headers = {k.lower(): v for k, v in request_headers.items()}
    propagated: dict[str, str] = {}
    for header_name in mcp_server.headers:
        value = lower_request_headers.get(header_name.lower())
        if value is not None:
            propagated[header_name] = value
    return propagated


def find_unresolved_auth_headers(
    configured: Mapping[str, str],
    resolved: Mapping[str, str],
) -> list[str]:
    """Return configured auth header names that are absent from the resolved headers.

    Comparison is case-insensitive so that ``Authorization`` and ``authorization``
    are treated as the same header name.

    Args:
        configured: The server's ``authorization_headers`` configuration mapping
            (header name → secret path or keyword).
        resolved: The fully resolved headers that will be sent to the MCP server.

    Returns:
        List of header names from ``configured`` that could not be resolved, i.e.
        are not present as a key in ``resolved``. An empty list means all headers
        were resolved successfully.
    """
    resolved_lower = {k.lower() for k in resolved}
    return [h for h in configured if h.lower() not in resolved_lower]


def build_server_headers(
    mcp_server: ModelContextProtocolServer,
    client_headers: dict[str, str],
    request_headers: Optional[Mapping[str, str]],
    token: Optional[str],
) -> dict[str, str]:
    """Build the complete set of headers for a single MCP server.

    Merges client-supplied headers, resolved authorization headers, and propagated
    request headers in priority order (highest first):

    1. Client-supplied headers (already present in ``client_headers``).
    2. Statically resolved authorization headers from configuration.
    3. Kubernetes Bearer token for headers configured with the ``kubernetes`` keyword.
       ``client`` and ``oauth`` keywords are skipped — those values are already
       provided by the client in source 1.
    4. Headers propagated from the incoming request via the server's allowlist.

    Args:
        mcp_server: MCP server configuration.
        client_headers: Headers already supplied by the client for this server.
        request_headers: Headers from the incoming HTTP request, or ``None``.
        token: Optional Kubernetes service-account token.

    Returns:
        Merged headers dictionary for the server. May be empty if no headers apply.
    """
    server_headers: dict[str, str] = dict(client_headers)
    existing_lower = {k.lower() for k in server_headers}

    for (
        header_name,
        resolved_value,
    ) in mcp_server.resolved_authorization_headers.items():
        if header_name.lower() in existing_lower:
            continue
        match resolved_value:
            case constants.MCP_AUTH_KUBERNETES:
                if token:
                    server_headers[header_name] = f"Bearer {token}"
                    existing_lower.add(header_name.lower())
            case constants.MCP_AUTH_CLIENT | constants.MCP_AUTH_OAUTH:
                pass  # client-provided; already included via the initial client_headers copy
            case _:
                server_headers[header_name] = resolved_value
                existing_lower.add(header_name.lower())

    if mcp_server.headers and request_headers is not None:
        propagated = extract_propagated_headers(mcp_server, request_headers)
        for h_name, h_value in propagated.items():
            if h_name.lower() not in existing_lower:
                server_headers[h_name] = h_value
                existing_lower.add(h_name.lower())

    return server_headers


def build_mcp_headers(
    config: AppConfig,
    mcp_headers: McpHeaders,
    request_headers: Optional[Mapping[str, str]],
    token: Optional[str] = None,
) -> McpHeaders:
    """Build complete MCP headers by merging all header sources for each MCP server.

    For each configured MCP server, combines four header sources (in priority order,
    highest first):

    1. Client-supplied headers from the ``MCP-HEADERS`` request header (keyed by server name).
    2. Statically resolved authorization headers from configuration (e.g. file-based secrets).
    3. Kubernetes Bearer token: when a header is configured with the ``kubernetes`` keyword,
       the supplied ``token`` is formatted as ``Bearer <token>`` and used as its value.
       ``client`` and ``oauth`` keywords are not resolved here — those values are already
       provided by the client in source 1.
    4. Headers propagated from the incoming request via the server's configured allowlist.

    Args:
        config: Application configuration containing mcp_servers.
        mcp_headers: Per-request headers from the client, keyed by MCP server name.
        request_headers: Headers from the incoming HTTP request used for allowlist
            propagation, or ``None`` when not available.
        token: Optional Kubernetes service-account token used to resolve headers
            configured with the ``kubernetes`` keyword.

    Returns:
        McpHeaders keyed by MCP server name with the complete merged set of headers.
        Servers that end up with no headers are omitted from the result.
    """
    if not config.mcp_servers:
        return {}

    complete: McpHeaders = {}

    for mcp_server in config.mcp_servers:
        server_headers = build_server_headers(
            mcp_server,
            dict(mcp_headers.get(mcp_server.name, {})),
            request_headers,
            token,
        )
        if server_headers:
            complete[mcp_server.name] = server_headers

    return complete

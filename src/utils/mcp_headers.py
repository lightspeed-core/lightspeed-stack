"""MCP headers handling."""

import json
from urllib.parse import urlparse

from fastapi import Request

from configuration import AppConfig
from log import get_logger

logger = get_logger(__name__)

type McpHeaders = dict[str, dict[str, str]]


async def mcp_headers_dependency(request: Request) -> McpHeaders:
    """Get the MCP headers dependency to passed to mcp servers.

    mcp headers is a json dictionary or mcp url paths and their respective headers

    Parameters:
        request (Request): The FastAPI request object.

    Returns:
        The mcp headers dictionary, or empty dictionary if not found or on json decoding error
    """
    return extract_mcp_headers(request)


def extract_mcp_headers(request: Request) -> McpHeaders:
    """Extract mcp headers from MCP-HEADERS header.

    If the header is missing, contains invalid JSON, or the decoded
    value is not a dictionary, an empty dictionary is returned.

    Parameters:
        request: The FastAPI request object

    Returns:
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

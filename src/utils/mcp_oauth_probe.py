"""Probe MCP server for OAuth and raise 401 with WWW-Authenticate when required."""

from typing import Optional
import aiohttp
from fastapi import HTTPException

from models.responses import UnauthorizedResponse

from log import get_logger

logger = get_logger(__name__)


async def probe_mcp_oauth_and_raise_401(
    url: str,
    authorization: Optional[str] = None,
) -> None:
    """Probe MCP endpoint and raise 401 only when the server responds with 401.

    Performs a GET to the given URL with the optional Authorization header.
    If the response status is 401, raises HTTPException with status 401 and
    WWW-Authenticate header when present. Otherwise returns without raising.

    Args:
        url: MCP server URL to probe.
        authorization: Optional Authorization header value (e.g. "Bearer <token>").
        chain_from: Exception to chain the HTTPException from when
            the server returns 401 (e.g. the original AuthenticationError).

    Returns:
        None. Raises only when the server responds with 401.

    Raises:
        HTTPException: 401 with WWW-Authenticate when the server returns 401.
    """
    cause = f"MCP server at {url} requires OAuth"
    error_response = UnauthorizedResponse(cause=cause)
    headers: Optional[dict[str, str]] = (
        {"Authorization": authorization} if authorization is not None else None
    )
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                print(resp.status)
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
        # Only raise on 401; connection/timeout are not 401, so do not raise

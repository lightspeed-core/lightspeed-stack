"""Thin MCP client wrapper for OKP RAG retrieval.

Wraps pydantic-ai's :class:`~pydantic_ai.mcp.MCPToolset` (FastMCP-backed,
streamable HTTP) to perform a single, programmatic search-tool call against the
RHOKP MCP server. No agent or LLM is involved: this is a pre-run retriever, so
the tool is invoked directly rather than exposed to a model.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from pydantic_ai.mcp import MCPToolset

from log import get_logger

logger = get_logger(__name__)


async def call_okp_search(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    url: str,
    tool_name: str,
    query: str,
    rows: int,
    headers: Optional[dict[str, str]] = None,
    timeout: Optional[float] = None,
    product: Optional[str] = None,
    product_version: Optional[str] = None,
) -> dict[str, Any]:
    """Call the RHOKP MCP search tool and return its structured result.

    Opens a short-lived streamable-HTTP MCP session, invokes ``tool_name`` with
    ``{"query": query, "rows": rows}`` (plus ``product``/``product_version``
    when supplied), and returns the tool's structured content. The session is
    opened and closed by
    :meth:`~pydantic_ai.mcp.MCPToolset.direct_call_tool`.

    Parameters:
        url: RHOKP MCP endpoint (streamable HTTP), e.g. ``http://host:8080/mcp``.
        tool_name: Name of the MCP search tool to call (e.g. ``search``).
        query: Raw user query string.
        rows: Maximum number of results to request (server clamps to 1..20).
        headers: Optional static request headers (e.g. authorization).
        timeout: Optional per-request timeout in seconds for init and read.
        product: Optional product filter passed to the MCP search tool; omitted
            from the tool args when None.
        product_version: Optional product-version filter passed to the MCP
            search tool; omitted from the tool args when None.

    Returns:
        The tool's structured content as a dict, e.g.
        ``{"response": {"docs": [...], "numFound": N}}``. Returns an empty dict
        when the server returns non-mapping content (nothing usable to map).

    Raises:
        Exception: Propagates transport- and tool-level errors from the MCP
            client (``tool_error_behavior="error"``). Callers are expected to
            handle failures and degrade gracefully.
    """
    toolset_kwargs: dict[str, Any] = {"tool_error_behavior": "error"}
    if headers:
        toolset_kwargs["headers"] = headers
    if timeout is not None:
        toolset_kwargs["init_timeout"] = timeout
        toolset_kwargs["read_timeout"] = timeout

    tool_args: dict[str, Any] = {"query": query, "rows": rows}
    if product is not None:
        tool_args["product"] = product
    if product_version is not None:
        tool_args["product_version"] = product_version

    toolset = MCPToolset(url, **toolset_kwargs)
    result = await toolset.direct_call_tool(tool_name, tool_args)

    if isinstance(result, Mapping):
        return dict(result)

    logger.warning(
        "OKP MCP tool %r returned non-mapping result of type %s; ignoring",
        tool_name,
        type(result).__name__,
    )
    return {}

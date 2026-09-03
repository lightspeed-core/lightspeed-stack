"""Discover builtin file-search tools when that provider is configured."""

from __future__ import annotations

from typing import Final

from fastapi import HTTPException
from ogx_client import APIConnectionError, APIStatusError, AsyncOgxClient
from ogx_client.types.shared.provider_info import ProviderInfo

from log import get_logger
from models.api.responses.error import ServiceUnavailableResponse
from models.common.tools import CatalogTool, CatalogToolParameter

logger = get_logger(__name__)

TOOL_RUNTIME_API: Final[str] = "tool_runtime"
FILE_SEARCH_PROVIDER_TYPE: Final[str] = "inline::file-search"
FILE_SEARCH_PROVIDER_ID: Final[str] = "file-search"
FILE_SEARCH_TOOLGROUP_ID: Final[str] = "builtin::file_search"
BUILTIN_SERVER_SOURCE: Final[str] = "builtin"

# OGX server-mode GET /v1/admin/tools is broken (admin deps / nested routers),
# so expose the known builtin::file_search catalog when the provider is present.
FILE_SEARCH_CATALOG_TOOLS: Final[list[CatalogTool]] = [
    CatalogTool(
        identifier="insert_into_memory",
        description="Insert documents into memory",
        parameters=[],
        provider_id=FILE_SEARCH_PROVIDER_ID,
        toolgroup_id=FILE_SEARCH_TOOLGROUP_ID,
        server_source=BUILTIN_SERVER_SOURCE,
        type="tool",
    ),
    CatalogTool(
        identifier="file_search",
        description="Search files for relevant information",
        parameters=[
            CatalogToolParameter(
                name="query",
                description=(
                    "The query to search for. Can be a natural language "
                    "sentence or keywords."
                ),
                parameter_type="string",
                required=True,
                default=None,
            )
        ],
        provider_id=FILE_SEARCH_PROVIDER_ID,
        toolgroup_id=FILE_SEARCH_TOOLGROUP_ID,
        server_source=BUILTIN_SERVER_SOURCE,
        type="tool",
    ),
]


def _is_file_search_provider(provider: ProviderInfo) -> bool:
    """Return whether a provider entry is a file-search tool runtime.

    Parameters:
        provider: Provider metadata from the backend.

    Returns:
        True when the provider implements file-search tool runtime.
    """
    return (
        provider.api == TOOL_RUNTIME_API
        and provider.provider_type == FILE_SEARCH_PROVIDER_TYPE
    )


async def get_file_search_tools(
    client: AsyncOgxClient,
) -> list[CatalogTool]:
    """Return builtin file-search tools when that provider is configured.

    Provider presence is checked via ``providers.list()``. Tool definitions are
    not fetched from ``/v1/admin/tools`` (broken in OGX server mode); the
    known ``builtin::file_search`` catalog is returned instead.

    Parameters:
        client: Initialized OGX client.

    Returns:
        Catalog tools for the configured file-search runtime, or an empty
        list when file search is not configured.
    """
    try:
        providers = await client.providers.list()
    except APIStatusError as exc:
        logger.warning("Unable to list providers for file-search tools: %s", exc)
        return []
    except APIConnectionError as e:
        logger.error("Unable to connect to OGX: %s", e)
        response = ServiceUnavailableResponse(
            backend_name="OGX", cause=str(e)
        ).model_dump()
        raise HTTPException(**response) from e

    file_search_provider = next(
        (provider for provider in providers if _is_file_search_provider(provider)),
        None,
    )
    if file_search_provider is None:
        logger.debug(
            "No %s provider configured",
            FILE_SEARCH_PROVIDER_TYPE,
        )
        return []

    logger.debug(
        "Using static catalog for %d file-search tools (toolgroup %s)",
        len(FILE_SEARCH_CATALOG_TOOLS),
        FILE_SEARCH_TOOLGROUP_ID,
    )
    return list(FILE_SEARCH_CATALOG_TOOLS)

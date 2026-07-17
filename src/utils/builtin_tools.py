"""Discover builtin file-search tools from Llama Stack when configured."""

from __future__ import annotations

from typing import Final

from fastapi import HTTPException
from ogx_client import APIConnectionError, APIStatusError, AsyncOgxClient
from ogx_client._base_client import make_request_options
from ogx_client.types.shared.provider_info import ProviderInfo

from log import get_logger
from models.api.responses.error import ServiceUnavailableResponse
from models.common.tools import CatalogTool, ListToolDefsResponse
from utils.tool_formatter import build_catalog_tool

logger = get_logger(__name__)

TOOL_RUNTIME_API: Final[str] = "tool_runtime"
FILE_SEARCH_PROVIDER_TYPE: Final[str] = "inline::file-search"
FILE_SEARCH_PROVIDER_ID: Final[str] = "file-search"
FILE_SEARCH_TOOLGROUP_ID: Final[str] = "builtin::file_search"
BUILTIN_SERVER_SOURCE: Final[str] = "builtin"


def _is_file_search_provider(provider: ProviderInfo) -> bool:
    """Return whether a provider entry is a file-search tool runtime.

    Parameters:
        provider: Provider metadata from Llama Stack.

    Returns:
        True when the provider implements file-search tool runtime.
    """
    return (
        provider.api == TOOL_RUNTIME_API
        and provider.provider_type == FILE_SEARCH_PROVIDER_TYPE
    )


async def get_file_search_tools_from_lls(
    client: AsyncOgxClient,
) -> list[CatalogTool]:
    """Discover builtin file-search tools from Llama Stack when configured.

    Llama Stack auto-registers built-in tool groups from configured
    ``tool_runtime`` providers. The public client SDK no longer exposes
    ``tools.list``, but the ``GET /v1/tools`` route remains available and
    returns tool definitions from the active runtime providers.

    Parameters:
        client: Initialized Llama Stack client.

    Returns:
        Catalog tools for the configured file-search runtime, or an empty
        list when file search is not configured or discovery fails.
    """
    try:
        providers = await client.providers.list()
    except APIStatusError as exc:
        logger.warning(
            "Unable to list Llama Stack providers for file-search tools: %s", exc
        )
        return []
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
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
            "No %s provider configured in Llama Stack",
            FILE_SEARCH_PROVIDER_TYPE,
        )
        return []

    try:
        response = await client.get(
            "/v1/tools",
            cast_to=ListToolDefsResponse,
            options=make_request_options(
                query={"toolgroup_id": FILE_SEARCH_TOOLGROUP_ID},
            ),
        )
    except APIStatusError as exc:
        logger.warning(
            "Unable to list file-search tools for toolgroup %s: %s",
            FILE_SEARCH_TOOLGROUP_ID,
            exc,
        )
        return []
    except APIConnectionError as e:
        logger.error("Unable to connect to Llama Stack: %s", e)
        response = ServiceUnavailableResponse(
            backend_name="OGX", cause=str(e)
        ).model_dump()
        raise HTTPException(**response) from e

    tools = [
        build_catalog_tool(
            tool,
            provider_id=FILE_SEARCH_PROVIDER_ID,
            toolgroup_id=FILE_SEARCH_TOOLGROUP_ID,
            server_source=BUILTIN_SERVER_SOURCE,
        )
        for tool in response.data
    ]
    logger.debug(
        "Retrieved %d file-search tools from Llama Stack toolgroup %s",
        len(tools),
        FILE_SEARCH_TOOLGROUP_ID,
    )
    return tools

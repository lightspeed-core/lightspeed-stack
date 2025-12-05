"""Common utilities for the project."""

import asyncio
from functools import wraps
from typing import Any, Callable, List, cast
from logging import Logger

from llama_stack_client import AsyncLlamaStackClient
from llama_stack import AsyncLlamaStackAsLibraryClient

from client import AsyncLlamaStackClientHolder
from models.config import Configuration, ModelContextProtocolServer


async def register_mcp_servers_async(
    logger: Logger, configuration: Configuration
) -> None:
    """Register Model Context Protocol (MCP) servers with the LlamaStack client (async).

    If no MCP servers are present in the provided configuration this function returns immediately.
    Selects between a library client (initializes it) and a service client based on
    configuration.llama_stack.use_as_library_client, then registers any MCP servers not already
    present in the client's toolgroups.

    Parameters:
        logger: Logger instance.
        configuration: Configuration containing the `mcp_servers` list and
        `llama_stack` client mode.

    Notes:
        - The `logger` parameter is used for debug/info logging and is
          intentionally undocumented as a common service.
        - Exceptions from the LlamaStack client (network/errors during
          initialization or registration) are not caught here and will
          propagate to the caller.
    """
    # Skip MCP registration if no MCP servers are configured
    if not configuration.mcp_servers:
        logger.debug("No MCP servers configured, skipping registration")
        return

    if configuration.llama_stack.use_as_library_client:
        # Library client - use async interface
        client = cast(
            AsyncLlamaStackAsLibraryClient, AsyncLlamaStackClientHolder().get_client()
        )
        await client.initialize()
        await _register_mcp_toolgroups_async(client, configuration.mcp_servers, logger)
    else:
        # Service client - also use async interface
        client = AsyncLlamaStackClientHolder().get_client()
        await _register_mcp_toolgroups_async(client, configuration.mcp_servers, logger)


async def _register_mcp_toolgroups_async(
    client: AsyncLlamaStackClient,
    mcp_servers: List[ModelContextProtocolServer],
    logger: Logger,
) -> None:
    """
    Register MCP (Model Context Protocol) toolgroups with a LlamaStack async client.

    Checks the client's existing toolgroups and registers any servers from `mcp_servers`
    whose `name` is not present in the client's `provider_resource_id` list. For each
    new server it calls the client's toolgroups.register with parameters:
    `toolgroup_id`=`mcp.name`, `provider_id`=`mcp.provider_id`, and
    `mcp_endpoint` containing the server `url`.

    This function performs network calls against the provided async client and does not
    catch exceptions raised by those calls — any exceptions from the client (e.g., RPC
    or HTTP errors) will propagate to the caller.
    """
    # Get registered tools
    registered_toolgroups = await client.toolgroups.list()
    registered_toolgroups_ids = [
        tool_group.provider_resource_id for tool_group in registered_toolgroups
    ]
    logger.debug("Registered toolgroups: %s", registered_toolgroups_ids)

    # Register toolgroups for MCP servers if not already registered
    for mcp in mcp_servers:
        if mcp.name not in registered_toolgroups_ids:
            logger.debug("Registering MCP server: %s, %s", mcp.name, mcp.url)

            registration_params = {
                "toolgroup_id": mcp.name,
                "provider_id": mcp.provider_id,
                "mcp_endpoint": {"uri": mcp.url},
            }

            await client.toolgroups.register(**registration_params)
            logger.debug("MCP server %s registered successfully", mcp.name)


def run_once_async(func: Callable) -> Callable:
    """
    Ensure that an async function is executed only once.

    On the first invocation the wrapped coroutine is scheduled as an
    asyncio.Task on the current running event loop and its Task is cached.
    Later invocations return/await the same Task, receiving the same result or
    propagated exception. Requires an active running event loop when the
    wrapped function is first called.
    """
    task = None

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        """
        Run the wrapped async function exactly once and return its (awaited) result on every call.

        On the first invocation this schedules the underlying coroutine as an
        asyncio.Task on the current running event loop and caches that task.
        Subsequent calls return the same awaited task result. Exceptions raised
        by the task propagate to callers. Requires an active running event loop
        when first called.
        """
        nonlocal task
        if task is None:
            loop = asyncio.get_running_loop()
            task = loop.create_task(func(*args, **kwargs))
        return await task

    return wrapper

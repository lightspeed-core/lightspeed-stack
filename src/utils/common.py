"""Common utilities for the project."""

import asyncio
from collections.abc import Callable
from functools import wraps
from logging import Logger
from typing import Any, cast

from llama_stack.core.library_client import AsyncLlamaStackAsLibraryClient
from llama_stack_client import APIConnectionError, AsyncLlamaStackClient

from client import AsyncLlamaStackClientHolder
from constants import DEFAULT_MAX_RETRIES, DEFAULT_RETRY_DELAY
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
    ----------
        logger: Logger instance.
        configuration: Configuration containing the `mcp_servers` list and
        `llama_stack` client mode.

    Notes:
    -----
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
        await _register_mcp_toolgroups_async(
            client,
            configuration.mcp_servers,
            logger,
            max_retries=configuration.llama_stack.max_retries,
            retry_delay=configuration.llama_stack.retry_delay,
        )
    else:
        # Service client - also use async interface
        client = AsyncLlamaStackClientHolder().get_client()
        await _register_mcp_toolgroups_async(
            client,
            configuration.mcp_servers,
            logger,
            max_retries=configuration.llama_stack.max_retries,
            retry_delay=configuration.llama_stack.retry_delay,
        )


async def _register_mcp_toolgroups_async(
    client: AsyncLlamaStackClient,
    mcp_servers: list[ModelContextProtocolServer],
    logger: Logger,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay: int = DEFAULT_RETRY_DELAY,
) -> None:
    """
    Register MCP (Model Context Protocol) toolgroups with a LlamaStack async client.

    Checks the client's existing toolgroups and registers any servers from `mcp_servers`
    whose `name` is not present in the client's `provider_resource_id` list. For each
    new server it calls the client's toolgroups.register with parameters:
    `toolgroup_id`=`mcp.name`, `provider_id`=`mcp.provider_id`, and
    `mcp_endpoint` containing the server `url`.

    This function performs network calls against the provided async client and retries
    on ``APIConnectionError`` up to ``max_retries`` times with a fixed ``retry_delay``
    between attempts. All other exceptions propagate immediately.

    Parameters:
    ----------
        client (AsyncLlamaStackClient): The LlamaStack async client used to
                                        query and register toolgroups.
        mcp_servers (List[ModelContextProtocolServer]): MCP server descriptors
                                                        to ensure are registered.
        logger (Logger): Logger used for debug messages about registration
                         progress.
        max_retries (int): Maximum number of connection attempts before giving up.
        retry_delay (int): Delay in seconds between retry attempts.

    Raises:
    ------
        APIConnectionError: If the client is unreachable after all retries.
    """
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")

    for attempt in range(max_retries):
        try:
            registered_toolgroups = await client.toolgroups.list()
            registered_toolgroups_ids = [
                tool_group.provider_resource_id for tool_group in registered_toolgroups
            ]
            logger.debug("Registered toolgroups: %s", registered_toolgroups_ids)

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
            return
        except APIConnectionError:
            if attempt == max_retries - 1:
                raise
            logger.warning(
                "MCP server registration failed (attempt %d/%d), retrying in %ds...",
                attempt + 1,
                max_retries,
                retry_delay,
            )
            await asyncio.sleep(retry_delay)


def run_once_async(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Ensure that an async function is executed only once.

    On the first invocation the wrapped coroutine is scheduled as an
    asyncio.Task on the current running event loop and its Task is cached.
    Later invocations return/await the same Task, receiving the same result or
    propagated exception. Requires an active running event loop when the
    wrapped function is first called.

    Returns:
        Any: The result produced by the wrapped coroutine, or the exception it
             raised propagated to callers.
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

        Returns:
            The awaited result of the wrapped coroutine.
        """
        nonlocal task
        if task is None:
            loop = asyncio.get_running_loop()
            task = loop.create_task(func(*args, **kwargs))
        return await task

    return wrapper

"""E2E test utilities for managing Llama Stack MCP toolgroups.

This module provides functions to unregister (delete) MCP-related toolgroups from
a running Llama Stack instance during end-to-end tests. These utilities are intended to
reset Llama Stack toolgroup state between scenarios that involve dynamic toolgroup registration,
such as when switching configurations or testing various MCP authentication methods.

Only applies when running Llama Stack as a separate service (server mode).
Requires E2E_LLAMA_STACK_URL or the combination of E2E_LLAMA_HOSTNAME and E2E_LLAMA_PORT
environment variables to locate the Llama Stack instance.
"""

import asyncio
import os

from llama_stack_client import (
    APIConnectionError,
    AsyncLlamaStackClient,
    APIStatusError,
)


def _get_llama_stack_client() -> AsyncLlamaStackClient:
    """Build an AsyncLlamaStackClient from env (for e2e test use)."""
    base_url = os.getenv("E2E_LLAMA_STACK_URL")
    if not base_url:
        host = os.getenv("E2E_LLAMA_HOSTNAME", "localhost")
        port = os.getenv("E2E_LLAMA_PORT", "8321")
        base_url = f"http://{host}:{port}"
    api_key = os.getenv("E2E_LLAMA_STACK_API_KEY", "xyzzy")
    timeout = int(os.getenv("E2E_LLAMA_STACK_TIMEOUT", "60"))
    return AsyncLlamaStackClient(base_url=base_url, api_key=api_key, timeout=timeout)


async def _unregister_toolgroup_async(identifier: str) -> None:
    """Unregister a toolgroup by identifier; return (provider_id, provider_shield_id) for restore."""
    client = _get_llama_stack_client()
    try:
        await client.toolgroups.unregister(identifier)
    except APIConnectionError:
        raise
    except APIStatusError as e:
        # 400 "not found": toolgroup already absent, scenario can proceed
        if e.status_code == 400 and "not found" in str(e).lower():
            return None
        raise
    finally:
        await client.close()


async def _unregister_mcp_toolgroups_async() -> None:
    """Unregister all MCP toolgroups."""
    client = _get_llama_stack_client()
    try:
        toolgroups = await client.toolgroups.list()
        for toolgroup in toolgroups:
            if (
                toolgroup.identifier
                and toolgroup.provider_id == "model-context-protocol"
            ):
                await _unregister_toolgroup_async(toolgroup.identifier)
    except APIConnectionError:
        raise
    finally:
        await client.close()


def unregister_mcp_toolgroups() -> None:
    """Unregister all MCP toolgroups."""
    asyncio.run(_unregister_mcp_toolgroups_async())

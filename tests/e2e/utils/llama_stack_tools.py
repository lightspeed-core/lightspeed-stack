"""E2E helpers to unregister and re-register Llama Stack shields via the client API.

Used by the @disable-shields tag: before the scenario we call client.shields.delete()
to unregister the shield; after the scenario we call client.shields.register()
to restore it. Only applies in server mode (Llama Stack as a separate service).
Requires E2E_LLAMA_STACK_URL or E2E_LLAMA_HOSTNAME/E2E_LLAMA_PORT.
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

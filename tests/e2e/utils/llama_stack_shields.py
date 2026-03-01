"""E2E helpers to unregister and re-register Llama Stack shields via the client API.

Used by the @disable-shields tag: before the scenario we call client.shields.delete()
to unregister the shield; after the scenario we call client.shields.register()
to restore it. Only applies in server mode (Llama Stack as a separate service).
Requires E2E_LLAMA_STACK_URL or E2E_LLAMA_HOSTNAME/E2E_LLAMA_PORT.
"""

import asyncio
import os
from typing import Optional

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


async def _unregister_shield_async(identifier: str) -> Optional[tuple[str, str]]:
    """Unregister a shield by identifier; return (provider_id, provider_shield_id) for restore."""
    client = _get_llama_stack_client()
    try:
        shields = await client.shields.list()
        provider_id = None
        provider_shield_id = None
        found = False
        for shield in shields:
            if getattr(shield, "identifier", None) == identifier:
                provider_id = getattr(shield, "provider_id", None)
                provider_shield_id = getattr(
                    shield, "provider_resource_id", None
                ) or getattr(shield, "provider_shield_id", None)
                found = True
                break
        if not found:
            # Shield not registered; nothing to delete, scenario can proceed
            return None
        try:
            await client.shields.delete(identifier)
        except APIConnectionError:
            raise
        except APIStatusError as e:
            # 400 "not found": shield already absent, scenario can proceed
            if e.status_code == 400 and "not found" in str(e).lower():
                return None
            raise
        if provider_id is not None and provider_shield_id is not None:
            return (provider_id, provider_shield_id)
        return None
    finally:
        await client.close()


async def _register_shield_async(
    shield_id: str,
    provider_id: str,
    provider_shield_id: str,
) -> None:
    """Register a shield (restore after unregister)."""
    client = _get_llama_stack_client()
    try:
        await client.shields.register(
            shield_id=shield_id,
            provider_id=provider_id,
            provider_shield_id=provider_shield_id,
        )
    finally:
        await client.close()


def unregister_shield(
    identifier: str = "llama-guard",
) -> Optional[tuple[str, str]]:
    """Unregister the shield via client.shields.delete(); return (provider_id, provider_shield_id)."""
    return asyncio.run(_unregister_shield_async(identifier))


def register_shield(
    shield_id: str = "llama-guard",
    provider_id: Optional[str] = None,
    provider_shield_id: Optional[str] = None,
) -> None:
    """Re-register the shield via client.shields.register()."""
    if not provider_id:
        provider_id = os.getenv("E2E_LLAMA_GUARD_PROVIDER_ID", "llama-guard")
    if not provider_shield_id:
        provider_shield_id = os.getenv(
            "E2E_LLAMA_GUARD_PROVIDER_SHIELD_ID",
            "openai/gpt-4o-mini",
        )
    asyncio.run(_register_shield_async(shield_id, provider_id, provider_shield_id))

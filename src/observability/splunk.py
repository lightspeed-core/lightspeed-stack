"""Async Splunk HEC client for sending telemetry events."""

import platform
import time
from typing import Any

import aiohttp

from configuration import configuration
from version import __version__
from log import get_logger

logger = get_logger(__name__)


def _get_hostname() -> str:
    """Get the hostname for Splunk event metadata."""
    return platform.node() or "unknown"


def _read_token_from_file(token_path: str) -> str | None:
    """Read HEC token from file path."""
    try:
        with open(token_path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError as e:
        logger.warning("Failed to read Splunk HEC token from %s: %s", token_path, e)
        return None


async def send_splunk_event(event: dict[str, Any], sourcetype: str) -> None:
    """Send an event to Splunk HEC.

    This function sends events asynchronously and handles failures gracefully
    by logging warnings instead of raising exceptions. This ensures that
    Splunk connectivity issues don't affect the main application flow.

    Args:
        event: The event payload to send.
        sourcetype: The Splunk sourcetype (e.g., "infer_with_llm", "infer_error").
    """
    splunk_config = configuration.splunk
    if splunk_config is None or not splunk_config.enabled:
        logger.debug("Splunk integration disabled, skipping event")
        return

    if not splunk_config.url or not splunk_config.token_path or not splunk_config.index:
        logger.warning("Splunk configuration incomplete, skipping event")
        return

    # Read token on each request to support rotation without restart
    token = _read_token_from_file(str(splunk_config.token_path))
    if not token:
        return

    payload = {
        "time": int(time.time()),
        "host": _get_hostname(),
        "source": f"{splunk_config.source} (v{__version__})",
        "sourcetype": sourcetype,
        "index": splunk_config.index,
        "event": event,
    }

    headers = {
        "Authorization": f"Splunk {token}",
        "Content-Type": "application/json",
    }

    timeout = aiohttp.ClientTimeout(total=splunk_config.timeout)
    connector = aiohttp.TCPConnector(ssl=splunk_config.verify_ssl)

    try:
        async with aiohttp.ClientSession(
            timeout=timeout, connector=connector
        ) as session:
            async with session.post(
                splunk_config.url, json=payload, headers=headers
            ) as response:
                if response.status >= 400:
                    body = await response.text()
                    logger.warning(
                        "Splunk HEC request failed with status %d: %s",
                        response.status,
                        body[:200],
                    )
    except aiohttp.ClientError as e:
        logger.warning("Splunk HEC request failed: %s", e)
    except TimeoutError:
        logger.warning("Splunk HEC request timed out after %ds", splunk_config.timeout)

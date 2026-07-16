"""Async Splunk HEC client for sending telemetry events."""

import asyncio
import platform
import time
from typing import Any, Optional

import aiohttp
from fastapi import BackgroundTasks

from configuration import configuration
from log import get_logger
from version import __version__

logger = get_logger(__name__)


def _get_hostname() -> str:
    """Get the hostname for Splunk event metadata."""
    return platform.node() or "unknown"


def _read_token_from_file(token_path: str) -> Optional[str]:
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


# Strong references for fire-and-forget telemetry tasks so they aren't
# garbage-collected before completion (the event loop only holds weak refs).
_fire_and_forget_tasks: set[asyncio.Task[None]] = set()


def _cleanup_fire_and_forget_task(task: asyncio.Task[None]) -> None:
    """Remove completed task from tracking and surface unexpected failures.

    Called as a done-callback on fire-and-forget asyncio tasks.  Without
    explicit retrieval of the task result, any exception raised inside
    ``send_splunk_event`` would go unobserved and trigger a noisy
    "Task exception was never retrieved" warning at garbage-collection time.
    """
    _fire_and_forget_tasks.discard(task)
    try:
        task.result()
    except asyncio.CancelledError:
        logger.debug("Splunk fire-and-forget task was cancelled")
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning("Splunk fire-and-forget task failed", exc_info=True)


def dispatch_splunk_event(
    event: dict[str, Any],
    sourcetype: str,
    background_tasks: Optional[BackgroundTasks] = None,
    fire_and_forget: bool = False,
) -> None:
    """Dispatch a Splunk event via BackgroundTasks or fire-and-forget.

    Centralizes the two dispatch strategies used across endpoints:

    - **BackgroundTasks** (default): FastAPI runs the send after the response
      completes.  Preferred for successful responses.
    - **fire-and-forget**: Creates an ``asyncio.Task`` directly, bypassing
      BackgroundTasks.  Required on error paths where FastAPI discards
      BackgroundTasks for non-2xx responses.

    No-op when ``background_tasks`` is None and ``fire_and_forget`` is False.

    Args:
        event: The Splunk event payload dict.
        sourcetype: Splunk sourcetype for the event.
        background_tasks: FastAPI background task manager, or None.
        fire_and_forget: When True, dispatch via ``asyncio.create_task()``
            instead of ``background_tasks``.
    """
    if fire_and_forget:
        task = asyncio.create_task(send_splunk_event(event, sourcetype))
        _fire_and_forget_tasks.add(task)
        task.add_done_callback(_cleanup_fire_and_forget_task)
    elif background_tasks is not None:
        background_tasks.add_task(send_splunk_event, event, sourcetype)

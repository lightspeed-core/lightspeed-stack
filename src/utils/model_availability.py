"""Verify that at least one model is registered with Llama Stack at startup."""

import asyncio
from typing import Final

from llama_stack_client import (
    APIConnectionError,
    APIStatusError,
    AsyncLlamaStackClient,
)

from log import get_logger

logger = get_logger(__name__)

_DEFAULT_MAX_RETRIES: Final[int] = 5
_DEFAULT_BASE_DELAY: Final[int] = 2


async def verify_models_available(
    client: AsyncLlamaStackClient,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    base_delay: int = _DEFAULT_BASE_DELAY,
) -> None:
    """Verify that at least one model is registered with Llama Stack.

    Fetches the model list from the connected Llama Stack instance and
    confirms it is non-empty.  Connection errors and empty model lists
    are retried with exponential backoff so that the service can wait
    for models to become available during concurrent startup.

    Args:
        client: The async Llama Stack client.
        max_retries: Maximum number of attempts before giving up.
        base_delay: Base delay in seconds for exponential backoff.

    Returns:
        None on success (at least one model found).

    Raises:
        APIConnectionError: If Llama Stack is unreachable after all retries.
        RuntimeError: If no models are registered after all retries.
    """
    for attempt in range(max_retries):
        try:
            models = await client.models.list()
            if models:
                model_ids = [m.id for m in models]
                logger.info(
                    "Found %d model(s): %s",
                    len(model_ids),
                    model_ids,
                )
                return
            # Empty list — treat as transient; retry unless exhausted
            if attempt == max_retries - 1:
                logger.error("No models registered after %d attempts", max_retries)
                raise RuntimeError(
                    f"No models registered in Llama Stack after {max_retries} attempts"
                )
            delay = base_delay * (2**attempt)
            logger.warning(
                "No models registered (attempt %d/%d), retrying in %ds...",
                attempt + 1,
                max_retries,
                delay,
            )
            await asyncio.sleep(delay)
        except (APIConnectionError, APIStatusError):
            if attempt == max_retries - 1:
                logger.error(
                    "Failed to connect to Llama Stack after %d attempts",
                    max_retries,
                )
                raise
            delay = base_delay * (2**attempt)
            logger.warning(
                "Llama Stack not reachable (attempt %d/%d), retrying in %ds...",
                attempt + 1,
                max_retries,
                delay,
            )
            await asyncio.sleep(delay)

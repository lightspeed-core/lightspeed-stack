"""Utility functions for working with Llama Stack shields."""

import logging
from typing import Any

from llama_stack_client import AsyncLlamaStackClient

import metrics

logger = logging.getLogger(__name__)


async def get_available_shields(client: AsyncLlamaStackClient) -> list[str]:
    """
    Discover and return available shield identifiers.

    Args:
        client: The Llama Stack client to query for available shields.

    Returns:
        List of shield identifiers that are available.
    """
    available_shields = [shield.identifier for shield in await client.shields.list()]
    if not available_shields:
        logger.info("No available shields. Disabling safety")
    else:
        logger.info("Available shields: %s", available_shields)
    return available_shields


def detect_shield_violations(output_items: list[Any]) -> bool:
    """
    Check output items for shield violations and update metrics.

    Iterates through output items looking for message items with refusal
    attributes. If a refusal is found, increments the validation error
    metric and logs a warning.

    Args:
        output_items: List of output items from the LLM response to check.

    Returns:
        True if a shield violation was detected, False otherwise.
    """
    for output_item in output_items:
        item_type = getattr(output_item, "type", None)
        if item_type == "message":
            refusal = getattr(output_item, "refusal", None)
            if refusal:
                # Metric for LLM validation errors (shield violations)
                metrics.llm_calls_validation_errors_total.inc()
                logger.warning("Shield violation detected: %s", refusal)
                return True
    return False

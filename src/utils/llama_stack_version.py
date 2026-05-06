"""Check if the Llama Stack version is supported by the LCS."""

import asyncio
import re

from llama_stack_client import APIConnectionError, AsyncLlamaStackClient
from semver import Version

from constants import (
    MAXIMAL_SUPPORTED_LLAMA_STACK_VERSION,
    MINIMAL_SUPPORTED_LLAMA_STACK_VERSION,
)
from log import get_logger

logger = get_logger(__name__)

# Retry settings for waiting on Llama Stack readiness during startup.
# When LCS runs as a sidecar alongside Llama Stack, both containers start
# concurrently and Llama Stack may not be ready when LCS attempts its
# first version check.
_DEFAULT_MAX_RETRIES = 5
_DEFAULT_RETRY_DELAY = 2


class InvalidLlamaStackVersionException(Exception):
    """Llama Stack version is not valid."""


async def check_llama_stack_version(
    client: AsyncLlamaStackClient,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    retry_delay: int = _DEFAULT_RETRY_DELAY,
) -> None:
    """
    Verify the connected Llama Stack's version is within the supported range.

    This coroutine fetches the Llama Stack version from the provided client
    and validates it against the configured minimal and maximal supported
    versions. Connection attempts are retried with a fixed delay to handle
    the case where Llama Stack is still starting up (e.g., when running as
    a sidecar in the same pod).

    Args:
        client: The async Llama Stack client.
        max_retries: Maximum number of connection attempts before giving up.
        retry_delay: Delay in seconds between retry attempts.

    Raises:
        APIConnectionError: If Llama Stack is unreachable after all retries.
        InvalidLlamaStackVersionException: If the detected version is outside
        the supported range or cannot be parsed.
    """
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")

    for attempt in range(max_retries):
        try:
            version_info = await client.inspect.version()
            compare_versions(
                version_info.version,
                MINIMAL_SUPPORTED_LLAMA_STACK_VERSION,
                MAXIMAL_SUPPORTED_LLAMA_STACK_VERSION,
            )
            return
        except APIConnectionError:
            if attempt == max_retries - 1:
                raise
            logger.warning(
                "Llama Stack not ready (attempt %d/%d), retrying in %ds...",
                attempt + 1,
                max_retries,
                retry_delay,
            )
            await asyncio.sleep(retry_delay)


def compare_versions(version_info: str, minimal: str, maximal: str) -> None:
    """
    Validate that a semver version string is within the inclusive [minimal, maximal] range.

    Parses `version_info`, `minimal`, and `maximal` with semver.Version.parse
    and compares them.  If the current version is lower than `minimal` or
    higher than `maximal`, an InvalidLlamaStackVersionException is raised.

    Parameters:
    ----------
        version_info (str): Semver version string to validate (must be
        parseable by semver.Version.parse).
        minimal (str): Minimum allowed semver version (inclusive).
        maximal (str): Maximum allowed semver version (inclusive).

    Raises:
    ------
        InvalidLlamaStackVersionException: If `version_info` is outside the
        inclusive range defined by `minimal` and `maximal`.
    """
    version_pattern = r"\d+\.\d+\.\d+"
    match = re.search(version_pattern, version_info)
    if not match:
        logger.warning(
            "Failed to extract version pattern from '%s'. Skipping version check.",
            version_info,
        )
        raise InvalidLlamaStackVersionException(
            f"Failed to extract version pattern from '{version_info}'. Skipping version check."
        )

    normalized_version = match.group(0)

    try:
        current_version = Version.parse(normalized_version)
    except ValueError as e:
        logger.warning("Failed to parse Llama Stack version '%s'.", version_info)
        raise InvalidLlamaStackVersionException(
            f"Failed to parse Llama Stack version '{version_info}'."
        ) from e

    minimal_version = Version.parse(minimal)
    maximal_version = Version.parse(maximal)
    logger.debug("Current version: %s", current_version)
    logger.debug("Minimal version: %s", minimal_version)
    logger.debug("Maximal version: %s", maximal_version)

    if current_version < minimal_version:
        raise InvalidLlamaStackVersionException(
            f"Llama Stack version >= {minimal_version} is required, but {current_version} is used"
        )
    if current_version > maximal_version:
        raise InvalidLlamaStackVersionException(
            f"Llama Stack version <= {maximal_version} is required, but {current_version} is used"
        )
    logger.info("Correct Llama Stack version : %s", current_version)

"""Check if the Llama Stack version is supported by the LCS."""

import logging

from semver import Version

from llama_stack_client._client import AsyncLlamaStackClient


from constants import (
    MINIMAL_SUPPORTED_LLAMA_STACK_VERSION,
    MAXIMAL_SUPPORTED_LLAMA_STACK_VERSION,
)

logger = logging.getLogger("utils.llama_stack_version")


class InvalidLlamaStackVersionException(Exception):
    """Llama Stack version is not valid."""


async def check_llama_stack_version(
    client: AsyncLlamaStackClient,
) -> None:
    """
    Verify the connected Llama Stack's version is within the supported range.

    This coroutine fetches the Llama Stack version from the
    provided client and validates it against the configured minimal
    and maximal supported versions. Raises
    InvalidLlamaStackVersionException if the detected version is
    outside the supported range.
    """
    version_info = await client.inspect.version()
    compare_versions(
        version_info.version,
        MINIMAL_SUPPORTED_LLAMA_STACK_VERSION,
        MAXIMAL_SUPPORTED_LLAMA_STACK_VERSION,
    )


def compare_versions(version_info: str, minimal: str, maximal: str) -> None:
    """
    Validate that a semver version string is within the inclusive [minimal, maximal] range.

    Parses `version_info`, `minimal`, and `maximal` with semver.Version.parse
    and compares them.  If the current version is lower than `minimal` or
    higher than `maximal`, an InvalidLlamaStackVersionException is raised.

    Parameters:
        version_info (str): Semver version string to validate (must be
        parseable by semver.Version.parse).
        minimal (str): Minimum allowed semver version (inclusive).
        maximal (str): Maximum allowed semver version (inclusive).

    Raises:
        InvalidLlamaStackVersionException: If `version_info` is outside the
        inclusive range defined by `minimal` and `maximal`.
    """
    current_version = Version.parse(version_info)
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

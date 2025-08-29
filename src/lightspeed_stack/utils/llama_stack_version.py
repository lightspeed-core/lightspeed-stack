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
    """Check if the Llama Stack version is supported by the LCS."""
    version_info = await client.inspect.version()
    compare_versions(
        version_info.version,
        MINIMAL_SUPPORTED_LLAMA_STACK_VERSION,
        MAXIMAL_SUPPORTED_LLAMA_STACK_VERSION,
    )


def compare_versions(version_info: str, minimal: str, maximal: str) -> None:
    """Compare current Llama Stack version with minimal and maximal allowed versions."""
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

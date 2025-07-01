"""LLama stack client retrieval."""

import logging

from llama_stack.distribution.library_client import (
    AsyncLlamaStackAsLibraryClient,  # type: ignore
    LlamaStackAsLibraryClient,  # type: ignore
)
from llama_stack_client import AsyncLlamaStackClient, LlamaStackClient  # type: ignore
from models.config import LLamaStackConfiguration

logger = logging.getLogger(__name__)


def get_llama_stack_client(
    llama_stack_config: LLamaStackConfiguration,
) -> LlamaStackClient:
    """Retrieve Llama stack client according to configuration."""
    if llama_stack_config.use_as_library_client is True:
        if llama_stack_config.library_client_config_path is not None:
            logger.info("Using Llama stack as library client")
            client = LlamaStackAsLibraryClient(
                llama_stack_config.library_client_config_path
            )
            client.initialize()
            return client
        msg = "Configuration problem: library_client_config_path option is not set"
        logger.error(msg)
        # tisnik: use custom exception there - with cause etc.
        raise Exception(msg)  # pylint: disable=broad-exception-raised
    logger.info("Using Llama stack running as a service")
    return LlamaStackClient(
        base_url=llama_stack_config.url, api_key=llama_stack_config.api_key
    )


async def get_async_llama_stack_client(
    llama_stack_config: LLamaStackConfiguration,
) -> AsyncLlamaStackClient:
    """Retrieve Async Llama stack client according to configuration."""
    if llama_stack_config.use_as_library_client is True:
        if llama_stack_config.library_client_config_path is not None:
            logger.info("Using Llama stack as library client")
            client = AsyncLlamaStackAsLibraryClient(
                llama_stack_config.library_client_config_path
            )
            await client.initialize()
            return client
        msg = "Configuration problem: library_client_config_path option is not set"
        logger.error(msg)
        # tisnik: use custom exception there - with cause etc.
        raise Exception(msg)  # pylint: disable=broad-exception-raised
    logger.info("Using Llama stack running as a service")
    return AsyncLlamaStackClient(
        base_url=llama_stack_config.url, api_key=llama_stack_config.api_key
    )

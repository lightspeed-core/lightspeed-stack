"""LLama stack client retrieval."""

import logging

from llama_stack.distribution.library_client import (
    AsyncLlamaStackAsLibraryClient,  # type: ignore
    LlamaStackAsLibraryClient,  # type: ignore
)
from llama_stack_client import AsyncLlamaStackClient, LlamaStackClient  # type: ignore
from models.config import LLamaStackConfiguration

logger = logging.getLogger(__name__)


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class LlamaStackClientHolder(metaclass=Singleton):

    def load(self, llama_stack_config: LLamaStackConfiguration):
        """Retrieve Llama stack client according to configuration."""
        if llama_stack_config.use_as_library_client is True:
            if llama_stack_config.library_client_config_path is not None:
                logger.info("Using Llama stack as library client")
                client = LlamaStackAsLibraryClient(
                    llama_stack_config.library_client_config_path
                )
                client.initialize()
                self._lsc = client
            else:
                msg = "Configuration problem: library_client_config_path option is not set"
                logger.error(msg)
                # tisnik: use custom exception there - with cause etc.
                raise Exception(msg)  # pylint: disable=broad-exception-raised

        else:
            logger.info("Using Llama stack running as a service")
            self._lsc = LlamaStackClient(
                base_url=llama_stack_config.url, api_key=llama_stack_config.api_key
            )

    def get_llama_stack_client(self) -> LlamaStackClient:
        return self._lsc


class AsyncLlamaStackClientHolder(metaclass=Singleton):

    async def load(self, llama_stack_config: LLamaStackConfiguration):
        """Retrieve Async Llama stack client according to configuration."""
        if llama_stack_config.use_as_library_client is True:
            if llama_stack_config.library_client_config_path is not None:
                logger.info("Using Llama stack as library client")
                client = AsyncLlamaStackAsLibraryClient(
                    llama_stack_config.library_client_config_path
                )
                await client.initialize()
                self._lsc = client
            else:
                msg = "Configuration problem: library_client_config_path option is not set"
                logger.error(msg)
                # tisnik: use custom exception there - with cause etc.
                raise Exception(msg)  # pylint: disable=broad-exception-raised
        else:
            logger.info("Using Llama stack running as a service")
            self._lsc = AsyncLlamaStackClient(
                base_url=llama_stack_config.url, api_key=llama_stack_config.api_key
            )

    def get_llama_stack_client(self) -> AsyncLlamaStackClient:
        return self._lsc


lsc_holder = LlamaStackClientHolder()
async_lsc_holder = AsyncLlamaStackClientHolder()

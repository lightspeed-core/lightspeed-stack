"""Llama Stack client retrieval class."""

import logging

from typing import Optional

from llama_stack import (
    AsyncLlamaStackAsLibraryClient,  # type: ignore
)
from llama_stack_client import AsyncLlamaStackClient  # type: ignore
from models.config import LlamaStackConfiguration
from utils.types import Singleton


logger = logging.getLogger(__name__)


class AsyncLlamaStackClientHolder(metaclass=Singleton):
    """Container for an initialised AsyncLlamaStackClient."""

    _lsc: Optional[AsyncLlamaStackClient] = None

    async def load(self, llama_stack_config: LlamaStackConfiguration) -> None:
        """
        Load and initialize the holder's AsyncLlamaStackClient according to the provided config.

        If `llama_stack_config.use_as_library_client` is set to True, a
        library-mode client is created using
        `llama_stack_config.library_client_config_path` and initialized before
        being stored.

        Otherwise, a service-mode client is created using
        `llama_stack_config.url` and optional `llama_stack_config.api_key`.
        The created client is stored on the instance for later retrieval via
        `get_client()`.

        Parameters:
            llama_stack_config (LlamaStackConfiguration): Configuration that
            selects client mode and provides either a library client config
            path or service connection details (URL and optional API key).

        Raises:
            ValueError: If `use_as_library_client` is True but
            `library_client_config_path` is not set.
        """
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
                raise ValueError(msg)
        else:
            logger.info("Using Llama stack running as a service")
            self._lsc = AsyncLlamaStackClient(
                base_url=llama_stack_config.url,
                api_key=(
                    llama_stack_config.api_key.get_secret_value()
                    if llama_stack_config.api_key is not None
                    else None
                ),
            )

    def get_client(self) -> AsyncLlamaStackClient:
        """
        Get the initialized client held by this holder.

        Returns:
            AsyncLlamaStackClient: The initialized client instance.

        Raises:
            RuntimeError: If the client has not been initialized; call `load(...)` first.
        """
        if not self._lsc:
            raise RuntimeError(
                "AsyncLlamaStackClient has not been initialised. Ensure 'load(..)' has been called."
            )
        return self._lsc

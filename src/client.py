"""LLama Stack client retrieval class."""

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
                raise ValueError(msg)
        else:
            logger.info("Using Llama stack running as a service")
            self._lsc = AsyncLlamaStackClient(
                base_url=llama_stack_config.url, api_key=llama_stack_config.api_key
            )

    def get_client(self) -> AsyncLlamaStackClient:
        """Return an initialised AsyncLlamaStackClient."""
        if not self._lsc:
            raise RuntimeError(
                "AsyncLlamaStackClient has not been initialised. Ensure 'load(..)' has been called."
            )
        return self._lsc

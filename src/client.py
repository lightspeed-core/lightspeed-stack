"""Llama Stack client retrieval class."""

import logging
import json

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
                base_url=llama_stack_config.url,
                api_key=(
                    llama_stack_config.api_key.get_secret_value()
                    if llama_stack_config.api_key is not None
                    else None
                ),
            )

    def get_client(self) -> AsyncLlamaStackClient:
        """Return an initialised AsyncLlamaStackClient."""
        if not self._lsc:
            raise RuntimeError(
                "AsyncLlamaStackClient has not been initialised. Ensure 'load(..)' has been called."
            )
        return self._lsc

    def set_client(self, new_client: AsyncLlamaStackClient) -> None:
        """
        Replace the currently stored AsyncLlamaStackClient instance.

        This method allows updating the client reference when
        configuration or runtime attributes have changed.
        """
        self._lsc = new_client

    def get_client_with_updated_azure_headers(
        self,
        access_token: str,
        api_base: str,
        api_version: str,
    ) -> AsyncLlamaStackClient:
        """Return a new client with updated Azure headers, preserving other headers."""
        if not self._lsc:
            raise RuntimeError(
                "AsyncLlamaStackClient has not been initialised. Ensure 'load(..)' has been called."
            )

        current_headers = self._lsc.default_headers if self._lsc else {}
        provider_data_json = current_headers.get("X-LlamaStack-Provider-Data")

        try:
            provider_data = json.loads(provider_data_json) if provider_data_json else {}
        except (json.JSONDecodeError, TypeError):
            provider_data = {}

        # Update only Azure-specific fields
        provider_data.update(
            {
                "azure_api_key": access_token,
                "azure_api_base": api_base,
                "azure_api_version": api_version,
                "azure_api_type": None,  # deprecated attribute
            }
        )

        updated_headers = {
            **current_headers,
            "X-LlamaStack-Provider-Data": json.dumps(provider_data),
        }
        return self._lsc.copy(set_default_headers=updated_headers)  # type: ignore

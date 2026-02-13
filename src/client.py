"""Llama Stack client retrieval class."""

import json
import os
import tempfile
from typing import Optional

import yaml
from fastapi import HTTPException
from llama_stack.core.library_client import AsyncLlamaStackAsLibraryClient
from llama_stack_client import APIConnectionError, AsyncLlamaStackClient  # type: ignore

from configuration import configuration
from llama_stack_configuration import enrich_byok_rag, YamlDumper
from models.config import LlamaStackConfiguration
from models.responses import ServiceUnavailableResponse
from utils.types import Singleton
from log import get_logger

logger = get_logger(__name__)


class AsyncLlamaStackClientHolder(metaclass=Singleton):
    """Container for an initialised AsyncLlamaStackClient."""

    _lsc: Optional[AsyncLlamaStackClient] = None
    _config_path: Optional[str] = None

    @property
    def is_library_client(self) -> bool:
        """Check if using library mode client."""
        return isinstance(self._lsc, AsyncLlamaStackAsLibraryClient)

    async def load(self, llama_stack_config: LlamaStackConfiguration) -> None:
        """Initialize the Llama Stack client based on configuration."""
        if self._lsc is not None:  # early stopping - client already initialized
            return

        if llama_stack_config.use_as_library_client:
            await self._load_library_client(llama_stack_config)
        else:
            self._load_service_client(llama_stack_config)

    async def _load_library_client(self, config: LlamaStackConfiguration) -> None:
        """Initialize client in library mode.

        Stores the final config path for use in reload.
        """
        if config.library_client_config_path is None:
            raise ValueError(
                "Configuration problem: library_client_config_path is not set"
            )
        logger.info("Using Llama stack as library client")

        byok_rag = [b.model_dump() for b in configuration.configuration.byok_rag]

        if byok_rag:  # BYOK RAG configured - enrich and store enriched path
            self._config_path = self._enrich_library_config(
                config.library_client_config_path, byok_rag
            )
        else:  # No RAG - store original path
            self._config_path = config.library_client_config_path

        client = AsyncLlamaStackAsLibraryClient(self._config_path)
        await client.initialize()
        self._lsc = client

    def _load_service_client(self, config: LlamaStackConfiguration) -> None:
        """Initialize client in service mode (remote HTTP)."""
        logger.info("Using Llama stack running as a service")
        logger.info(
            "Using timeout of %d seconds for Llama Stack requests", config.timeout
        )
        api_key = config.api_key.get_secret_value() if config.api_key else None
        # Convert AnyHttpUrl to string for the client
        base_url = str(config.url) if config.url else None
        self._lsc = AsyncLlamaStackClient(
            base_url=base_url, api_key=api_key, timeout=config.timeout
        )

    def _enrich_library_config(
        self, input_config_path: str, byok_rag: list[dict]
    ) -> str:
        """Enrich llama-stack config with BYOK RAG settings.

        Only called when BYOK RAG is configured.
        """
        try:
            with open(input_config_path, "r", encoding="utf-8") as f:
                ls_config = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as e:
            logger.warning("Failed to read llama-stack config: %s", e)
            return input_config_path

        enrich_byok_rag(ls_config, byok_rag)

        enriched_path = os.path.join(
            tempfile.gettempdir(), "llama_stack_enriched_config.yaml"
        )

        try:
            with open(enriched_path, "w", encoding="utf-8") as f:
                yaml.dump(ls_config, f, Dumper=YamlDumper, default_flow_style=False)
            logger.info("Wrote enriched llama-stack config to %s", enriched_path)
            return enriched_path
        except OSError as e:
            logger.warning("Failed to write enriched config: %s", e)
            return input_config_path

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

    async def reload_library_client(self) -> AsyncLlamaStackClient:
        """Reload library client to pick up env var changes.

        For use with library mode only.

        Returns:
            The reloaded client instance.
        """
        if not self._config_path:
            raise RuntimeError("Cannot reload: config path not set")
        try:
            client = AsyncLlamaStackAsLibraryClient(self._config_path)
            await client.initialize()
        except APIConnectionError as e:
            error_response = ServiceUnavailableResponse(
                backend_name="Llama Stack",
                cause=str(e),
            )
            raise HTTPException(**error_response.model_dump()) from e
        self._lsc = client
        return client

    def update_provider_data(self, updates: dict[str, str]) -> AsyncLlamaStackClient:
        """Update provider data headers for service client.

        For use with service mode only.

        Args:
            updates: Key-value pairs to merge into provider data header.

        Returns:
            The updated client instance.
        """
        if not self._lsc:
            raise RuntimeError(
                "AsyncLlamaStackClient has not been initialised. Ensure 'load(..)' has been called."
            )

        current_headers = self._lsc.default_headers or {}
        provider_data_json = current_headers.get("X-LlamaStack-Provider-Data")

        try:
            provider_data = json.loads(provider_data_json) if provider_data_json else {}
        except (json.JSONDecodeError, TypeError):
            provider_data = {}

        provider_data.update(updates)

        updated_headers = {
            **current_headers,
            "X-LlamaStack-Provider-Data": json.dumps(provider_data),
        }

        self._lsc = self._lsc.copy(set_default_headers=updated_headers)  # type: ignore
        return self._lsc

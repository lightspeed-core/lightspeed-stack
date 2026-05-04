"""Llama Stack client retrieval class."""

import json
import os
import tempfile
from typing import Optional, cast

import yaml
from fastapi import HTTPException
from llama_stack.core.library_client import AsyncLlamaStackAsLibraryClient
from llama_stack_client import APIConnectionError, APIStatusError, AsyncLlamaStackClient

import constants
from authorization.azure_token_manager import AzureEntraIDManager
from configuration import configuration
from llama_stack_configuration import (
    YamlDumper,
    enrich_azure_entra_id_inference,
    enrich_byok_rag,
    enrich_solr,
    synthesize_to_file,
)
from log import get_logger
from models.api.responses.error import ServiceUnavailableResponse
from models.config import LlamaStackConfiguration
from utils.types import Singleton

logger = get_logger(__file__)


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

        Forks on configuration shape: legacy mode (a library_client_config_path
        with no unified config block) enriches the operator-supplied run.yaml;
        every other library-mode shape is unified and synthesizes a fresh
        run.yaml. The root Configuration validator guarantees a run source
        exists and that the legacy path never coexists with unified inputs, so
        "has a legacy path and no config block" is a sufficient legacy signal
        here — a unified config driven only by the root-level
        inference.providers (with no config block) correctly falls through to
        synthesis. Stores the final config path for use in reload.
        """
        logger.info("Using Llama stack as library client")

        if config.library_client_config_path is not None and config.config is None:
            self._config_path = self._enrich_library_config(
                config.library_client_config_path
            )
        else:
            self._config_path = self._synthesize_library_config()

        client = AsyncLlamaStackAsLibraryClient(self._config_path)
        await client.initialize()
        self._lsc = client

    def _synthesize_library_config(self) -> str:
        """Synthesize a unified-mode run.yaml and return its on-disk path.

        Reads the operator's lightspeed-stack.yaml (the same file the workers
        loaded, located via LIGHTSPEED_STACK_CONFIG_PATH) as a raw dict so the
        synthesizer sees exactly what the operator wrote, then writes the
        synthesized run.yaml to the persistent path (overwritten each boot,
        mode 0600). The path can be overridden via the
        LIGHTSPEED_STACK_SYNTHESIZED_CONFIG_PATH env var
        (set from --synthesized-config-output).
        """
        config_file = os.environ.get(constants.CONFIG_PATH_ENV_VAR)
        if not config_file:
            raise ValueError(
                f"Cannot synthesize Llama Stack config: {constants.CONFIG_PATH_ENV_VAR} "
                "is not set"
            )

        with open(config_file, "r", encoding="utf-8") as f:
            lcs_config = yaml.safe_load(f)

        output_path = os.environ.get(
            constants.SYNTHESIZED_CONFIG_PATH_ENV_VAR,
            constants.DEFAULT_SYNTHESIZED_CONFIG_PATH,
        )
        config_file_dir = os.path.dirname(os.path.abspath(config_file))

        synthesize_to_file(lcs_config, output_path, config_file_dir)
        logger.info("Using synthesized Llama Stack config at %s", output_path)
        return output_path

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

    def _enrich_library_config(self, input_config_path: str) -> str:
        """Enrich llama-stack config with BYOK RAG and OKP Solr settings."""
        try:
            with open(input_config_path, "r", encoding="utf-8") as f:
                ls_config = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as e:
            logger.warning("Failed to read llama-stack config: %s", e)
            return input_config_path

        config = configuration.configuration

        # Enrichment: BYOK RAG
        enrich_byok_rag(ls_config, [b.model_dump() for b in config.byok_rag])

        # Enrichment: Solr - enabled when "okp" appears in either inline or tool list
        enrich_solr(ls_config, config.rag.model_dump(), config.okp.model_dump())

        # Enrichment: Azure Entra ID deferred auth
        entra_id_config = (
            config.azure_entra_id.model_dump() if config.azure_entra_id else None
        )
        enrich_azure_entra_id_inference(ls_config, entra_id_config)

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

    async def check_model_available(self, model_id: str) -> tuple[bool, str]:
        """Check if a model is available in the registry, attempting reload if needed.

        Verifies the model can be found in the Llama Stack client's model
        list. If the model is missing and the client is running in library
        mode, attempts a client reload to re-register models before
        reporting failure.

        The reload re-runs the full Stack initialization pipeline, which
        re-attempts model registration with providers. This handles the
        case where a transient provider failure (e.g. Vertex AI network
        blip) caused model registration to fail on startup. Since
        Kubernetes readiness probe failures only remove the pod from
        service endpoints without restarting it, the reload provides a
        self-healing path.

        Args:
            model_id: The expected model identifier to look up.

        Returns:
            A tuple of (available, reason) where available is True if the
            model was found, and reason describes the outcome.
        """
        try:
            client = self.get_client()
            models = await client.models.list()
        except RuntimeError as e:
            logger.warning("Client not initialized, skipping model check: %s", e)
            return False, f"Client not initialized: {e!s}"
        except (APIConnectionError, APIStatusError) as e:
            logger.error("Error checking model availability: %s", e)
            return False, f"Error checking model availability: {e!s}"

        if any(m.id == model_id for m in models):
            return True, f"Model {model_id} is available"

        # Model not found - attempt self-healing reload for library clients.
        # In server mode there is no library client to reload, so we can
        # only detect the missing model and report failure.
        if self.is_library_client:
            logger.warning(
                "Model %s not found, attempting client reload",
                model_id,
            )
            try:
                await self.reload_library_client()
                client = self.get_client()
                reloaded_models = await client.models.list()
                if any(m.id == model_id for m in reloaded_models):
                    logger.info(
                        "Model %s found after client reload",
                        model_id,
                    )
                    return True, f"Model {model_id} is available after reload"
            except (
                RuntimeError,
                HTTPException,
                APIConnectionError,
                APIStatusError,
            ) as err:
                logger.error("Client reload failed: %s", err)

        registered_ids = [m.id for m in models]
        logger.error(
            "Model %s not found in registry. Registered models: %s",
            model_id,
            registered_ids,
        )
        return False, f"Model {model_id} not found in model registry"

    async def update_azure_token(self) -> AsyncLlamaStackClient:
        """Apply cached Azure credentials and replace the held client.

        Returns:
            The new client instance assigned to this holder.
        """
        updates = AzureEntraIDManager().build_azure_provider_data()
        if not updates:
            return self.get_client()

        if self.is_library_client:
            if not self._config_path:
                logger.warning("Cannot update Azure token: config path not set")
                return self.get_client()

            current_provider_data = dict(
                cast(AsyncLlamaStackAsLibraryClient, self._lsc).provider_data or {}
            )
            current_provider_data.update(updates)
            client = AsyncLlamaStackAsLibraryClient(
                self._config_path, provider_data=current_provider_data
            )
            await client.initialize()
            self._lsc = client
            return client

        # Service client mode
        current_client = self.get_client()
        current_headers = current_client.default_headers or {}
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

        updated_client = current_client.copy(
            set_default_headers=updated_headers  # type: ignore[arg-type]
        )
        self._lsc = updated_client
        return updated_client

    async def get_azure_base_url(self) -> Optional[str]:
        """
        Retrieve the Azure base_url endpoint from the remote Llama Stack provider configuration.

        Returns:
            Optional[str]: The Azure base_url if available, otherwise None.
        """
        if not self._lsc:
            return None

        try:
            providers = await self._lsc.providers.list()
        except (APIConnectionError, APIStatusError) as err:
            logger.warning("Failed to list providers for Azure base_url: %s", err)
            return None

        for provider in providers:
            if provider.provider_type != "remote::azure":
                continue
            base = provider.config.get("base_url")
            if base is not None:
                return str(base)
        return None

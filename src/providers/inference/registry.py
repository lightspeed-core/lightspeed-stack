"""Singleton registry of initialized inference providers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, Optional

from providers.inference.azure.provider import AzureInferenceProvider
from providers.inference.bedrock.provider import BedrockInferenceProvider
from providers.inference.errors import ProviderNotFoundError
from providers.inference.openai.provider import OpenAIInferenceProvider
from providers.inference.sentence_transformers.provider import (
    SentenceTransformersInferenceProvider,
)
from providers.inference.vertexai.provider import VertexAIInferenceProvider
from providers.inference.watsonx.provider import WatsonxInferenceProvider
from utils.types import Singleton

if TYPE_CHECKING:
    from models.config import InferenceConfiguration
    from providers.inference.base import InferenceProvider
    from providers.inference.catalog import CatalogModel
    from providers.inference.types import ModelType, ProviderId, ProviderType

PROVIDER_CLASSES: Final[dict[ProviderType, type[InferenceProvider[Any, Any]]]] = {
    "openai": OpenAIInferenceProvider,
    "azure": AzureInferenceProvider,
    "vertexai": VertexAIInferenceProvider,
    "bedrock": BedrockInferenceProvider,
    "watsonx": WatsonxInferenceProvider,
    "sentence_transformers": SentenceTransformersInferenceProvider,
}


class ProviderRegistry(metaclass=Singleton):
    """Registry of initialized inference providers."""

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._providers: dict[ProviderId, InferenceProvider[Any, Any]] = {}

    async def initialize(self, inference: InferenceConfiguration) -> None:
        """Register and initialize providers from configuration.

        Args:
            inference: Inference provider configuration to load at startup.

        """
        for entry in inference.providers:
            provider_cls = PROVIDER_CLASSES[entry.type]
            provider = provider_cls(entry)
            await provider.initialize()
            self._providers[provider.provider_id] = provider

    def find_provider(
        self, provider_id: ProviderId
    ) -> Optional[InferenceProvider[Any, Any]]:
        """Find a provider by ID when absence is acceptable.

        Args:
            provider_id: Local provider identifier from configuration.

        Returns:
            The initialized provider, or None if it is not registered.

        """
        return self._providers.get(provider_id)

    def get_provider(self, provider_id: ProviderId) -> InferenceProvider[Any, Any]:
        """Get a provider by ID when absence is an error.

        Args:
            provider_id: Local provider identifier from configuration.

        Returns:
            The initialized provider.

        Raises:
            ProviderNotFoundError: If the provider is not registered.

        """
        if (provider := self.find_provider(provider_id)) is None:
            raise ProviderNotFoundError(provider_id)
        return provider

    def list_providers(self) -> list[InferenceProvider[Any, Any]]:
        """List initialized providers in registration order."""
        return list(self._providers.values())

    def list_models(
        self,
        model_type: Optional[ModelType] = None,
    ) -> list[CatalogModel]:
        """List cached catalog models across all providers.

        Args:
            model_type: Optional capability filter applied to each provider.

        Returns:
            Deep copies of cached catalog models matching the requested type,
            if specified.

        """
        models: list[CatalogModel] = []
        for provider in self._providers.values():
            models.extend(provider.list_catalog_models(model_type=model_type))
        return models

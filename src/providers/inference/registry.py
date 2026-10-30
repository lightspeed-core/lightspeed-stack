"""Singleton registry of initialized inference providers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, Literal, Optional, overload

from pydantic_ai.embeddings import EmbeddingModel
from pydantic_ai.models import Model
from sentence_transformers import CrossEncoder

from providers.inference.azure.provider import AzureInferenceProvider
from providers.inference.bedrock.provider import BedrockInferenceProvider
from providers.inference.errors import (
    NoModelConfiguredError,
    ProviderNotFoundError,
)
from providers.inference.openai.provider import OpenAIInferenceProvider
from providers.inference.resolve import configured_defaults, conversation_last_used
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

    @overload
    def resolve_model_instance(
        self,
        model_type: Literal["llm"],
        provider_id: Optional[ProviderId] = None,
        model_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Model: ...

    @overload
    def resolve_model_instance(
        self,
        model_type: Literal["embedding"],
        provider_id: ProviderId,
        model_id: str,
    ) -> EmbeddingModel: ...

    @overload
    def resolve_model_instance(
        self,
        model_type: Literal["rerank"],
        provider_id: ProviderId,
        model_id: str,
    ) -> CrossEncoder: ...

    def resolve_model_instance(
        self,
        model_type: ModelType,
        provider_id: Optional[ProviderId] = None,
        model_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Model | EmbeddingModel | CrossEncoder:
        """Resolve a typed model instance from the cached provider catalog.

        Embedding and rerank require both ``provider_id`` and ``model_id``.
        For llm those ids may be omitted; resolution then falls through
        conversation last-used, configured defaults, then the first available llm.

        Args:
            model_type: Required model capability to resolve.
            provider_id: Local provider id; required for embedding and rerank.
            model_id: Local catalog model name; required for embedding and rerank.
            conversation_id: Optional conversation used for llm last-used fallback.

        Returns:
            A per-request Model, EmbeddingModel, or CrossEncoder instance.

        Raises:
            ProviderNotFoundError: Explicit provider id is not registered.
            ModelNotAvailableError: Explicit model is missing from the catalog.
            NoModelConfiguredError: No llm remains after soft fallbacks.

        """
        if provider_id is not None and model_id is not None:
            return self._get_model_instance(provider_id, model_id, model_type)

        # Soft fallbacks (llm only): conversation last-used → defaults → first llm.
        if last_used := conversation_last_used(conversation_id):
            last_provider_id, last_model_id = last_used
            if self._is_llm_available(last_provider_id, last_model_id):
                return self._get_model_instance(last_provider_id, last_model_id, "llm")

        if defaults := configured_defaults():
            default_provider_id, default_model_id = defaults
            if self._is_llm_available(default_provider_id, default_model_id):
                return self._get_model_instance(
                    default_provider_id, default_model_id, "llm"
                )

        if instance := self._first_available_llm():
            return instance

        raise NoModelConfiguredError("llm")

    def _get_model_instance(
        self,
        provider_id: ProviderId,
        model_id: str,
        model_type: ModelType,
    ) -> Model | EmbeddingModel | CrossEncoder:
        """Get a typed model instance from a registered provider.

        Args:
            provider_id: Local provider id.
            model_id: Local catalog model name.
            model_type: Required model capability.

        Returns:
            The instantiated model for the requested type.

        Raises:
            ProviderNotFoundError: Provider id is not registered.
            ModelNotAvailableError: Model id is not in the catalog.

        """
        return self.get_provider(provider_id).get_model_instance(model_id, model_type)

    def _is_llm_available(self, provider_id: ProviderId, model_id: str) -> bool:
        """Return whether an llm catalog pair exists for the provider.

        Args:
            provider_id: Candidate provider id.
            model_id: Candidate local catalog model name.

        Returns:
            True when the provider is registered and exposes the llm.

        """
        if provider := self.find_provider(provider_id):
            return provider.get_catalog_model(model_id, "llm") is not None
        return False

    def _first_available_llm(self) -> Optional[Model]:
        """Return the first llm instance from registration order.

        Returns:
            The first available llm instance, or None when the catalog has none.

        """
        for provider in self.list_providers():
            models = provider.list_catalog_models(model_type="llm")
            if models:
                return provider.get_model_instance(models[0].name, "llm")
        return None

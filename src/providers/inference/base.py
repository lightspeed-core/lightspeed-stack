"""Abstract base class for inference providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, Literal, Optional, TypeVar, overload

from pydantic_ai.embeddings import EmbeddingModel
from pydantic_ai.models import Model
from pydantic_ai.providers import Provider
from sentence_transformers import CrossEncoder

from log import get_logger
from models.config import (
    AllowedModel,
    InferenceProviderEntryBase,
)
from providers.inference.catalog import CatalogModel, DiscoveredModel
from providers.inference.errors import ModelNotAvailableError

if TYPE_CHECKING:
    from providers.inference.types import ModelType, ProviderId

logger = get_logger(__name__)

EntryT = TypeVar("EntryT", bound=InferenceProviderEntryBase)
ProviderT = TypeVar("ProviderT", bound=Provider[Any])


class InferenceProvider(ABC, Generic[EntryT, ProviderT]):  # noqa: UP046
    """Runtime inference provider with a cached model catalog."""

    def __init__(self, entry: EntryT) -> None:
        """Initialize the inference provider.

        Args:
            entry: Provider configuration entry containing the provider ID,
                model discovery settings, and allowed models.

        """
        self.provider_id: ProviderId = entry.id
        self._provider: Optional[ProviderT] = None
        self._models: list[CatalogModel] = []
        self._entry: EntryT = entry

    @property
    def _get_provider(self) -> ProviderT:
        """Return the initialized PAI provider.

        Raises:
            RuntimeError: If the provider has not been initialized or does not
                use a PAI provider instance.

        """
        if self._provider is None:
            raise RuntimeError(
                f"Provider {self.provider_id!r} has not been initialized"
            )
        return self._provider

    async def initialize(self) -> None:
        """Build the PydanticAI provider and load the model catalog.

        Callers construct the subclass, then call this method to finish async setup.
        """
        self._provider = self._build_provider()
        self._models = await self._load_catalog()

    @abstractmethod
    def _build_provider(self) -> Optional[ProviderT]:
        """Build the PydanticAI provider.

        Returns:
            The configured PydanticAI provider, or None when the integration
            does not require a separate provider instance.

        """

    @abstractmethod
    async def _discover_models(self) -> list[DiscoveredModel]:
        """Discover models available from the provider.

        Returns:
            The models discovered from the provider, before applying the
            configured allow-list.

        """

    @abstractmethod
    def _create_llm(self, model: CatalogModel) -> Model:
        """Create an LLM from a catalog model.

        Args:
            model: Catalog entry describing the LLM to instantiate.

        Returns:
            The instantiated PydanticAI model.

        """

    @abstractmethod
    def _create_embedding(self, model: CatalogModel) -> EmbeddingModel:
        """Create an embedding model from a catalog model.

        Args:
            model: Catalog entry describing the embedding model to instantiate.

        Returns:
            The instantiated embedding model.

        """

    @abstractmethod
    def _create_rerank(self, model: CatalogModel) -> CrossEncoder:
        """Create a reranker from a catalog model.

        Args:
            model: Catalog entry describing the reranker to instantiate.

        Returns:
            The instantiated reranking model.

        """

    @abstractmethod
    def _infer_model_type(
        self,
        provider_model_id: str,
        **kwargs: Any,
    ) -> Optional[ModelType]:
        """Infer the type of a provider model.

        Args:
            provider_model_id: Model identifier used by the inference provider.
            **kwargs: Additional provider-specific attributes used for classification.

        Returns:
            The inferred model type, or None when the model is unsupported and
            should be omitted from discovery.

        """

    def list_catalog_models(
        self,
        model_type: Optional[ModelType] = None,
    ) -> list[CatalogModel]:
        """List catalog models, optionally filtered by model type.

        Args:
            model_type: Optional capability to filter by.

        Returns:
            Deep copies of matching catalog models, including nested metadata.

        """
        models = self._models
        if model_type is not None:
            models = [model for model in models if model.model_type == model_type]

        return [model.model_copy(deep=True) for model in models]

    def get_catalog_model(
        self,
        name: str,
        model_type: ModelType,
    ) -> Optional[CatalogModel]:
        """Get a catalog model by its local name and type.

        Args:
            name: Local catalog name of the model.
            model_type: Required model capability.

        Returns:
            A deep copy of the matching catalog model (including nested
            metadata), or None if no model matches both the specified name
            and type.

        """
        model = next(
            (
                candidate
                for candidate in self._models
                if candidate.name == name and candidate.model_type == model_type
            ),
            None,
        )
        return None if model is None else model.model_copy(deep=True)

    @overload
    def get_model_instance(self, name: str, model_type: Literal["llm"]) -> Model: ...

    @overload
    def get_model_instance(
        self, name: str, model_type: Literal["embedding"]
    ) -> EmbeddingModel: ...

    @overload
    def get_model_instance(
        self, name: str, model_type: Literal["rerank"]
    ) -> CrossEncoder: ...

    def get_model_instance(
        self, name: str, model_type: ModelType
    ) -> Model | EmbeddingModel | CrossEncoder:
        """Get a model instance by local catalog name and type.

        Args:
            name: Local catalog name of the model.
            model_type: Required model capability.

        Returns:
            The instantiated model for the requested type.

        Raises:
            ModelNotAvailableError: If no catalog entry matches both the
                specified name and type.

        """
        model = self.get_catalog_model(name, model_type)
        if model is None:
            raise ModelNotAvailableError(name, model_type, self.provider_id)

        match model_type:
            case "llm":
                return self._create_llm(model)
            case "embedding":
                return self._create_embedding(model)
            case _:  # rerank
                return self._create_rerank(model)

    async def _load_catalog(self) -> list[CatalogModel]:
        """Load the catalog and apply the configured model allow-list.

        When model discovery is disabled, constructs the catalog directly
        from the explicitly configured allowed models.

        Returns:
            The initialized catalog containing discovered or explicitly
            configured models, filtered according to provider configuration.

        """
        allowed_models = self._entry.allowed_models

        if self._entry.skip_model_discovery:
            return [
                CatalogModel(
                    name=allowed.name,
                    provider_model_id=allowed.provider_model_id,
                    model_type=allowed.model_type
                    or self._infer_model_type(allowed.provider_model_id)
                    or "llm",
                    metadata=dict(allowed.metadata),
                )
                for allowed in allowed_models
            ]

        discovered = await self._discover_models()
        return self._filter_discovered(discovered, allowed_models)

    def _filter_discovered(
        self,
        discovered: list[DiscoveredModel],
        allowed_models: list[AllowedModel],
    ) -> list[CatalogModel]:
        """Filter discovered models using the configured allow-list.

        Configured local names and metadata override the corresponding
        discovered catalog values. Models that are configured but not
        discovered are omitted.

        Args:
            discovered: Models returned by provider discovery.
            allowed_models: Explicitly allowed models from provider
                configuration.

        Returns:
            The filtered catalog. If no allow-list is configured, returns
            a copy of the discovered models.

        """
        if not allowed_models:
            return [
                CatalogModel(
                    name=model.provider_model_id,
                    provider_model_id=model.provider_model_id,
                    model_type=model.model_type,
                    metadata=model.metadata,
                )
                for model in discovered
            ]

        discovered_by_model_id = {
            model.provider_model_id: model for model in discovered
        }

        filtered: list[CatalogModel] = []

        for allowed in allowed_models:
            model = discovered_by_model_id.get(allowed.provider_model_id)

            if model is None:
                logger.warning(
                    "Configured model %r with provider model ID %r "
                    "was not discovered for provider %r",
                    allowed.name,
                    allowed.provider_model_id,
                    self.provider_id,
                )
                continue

            filtered.append(
                CatalogModel(
                    name=allowed.name,
                    provider_model_id=allowed.provider_model_id,
                    model_type=allowed.model_type or model.model_type,
                    metadata={**model.metadata, **allowed.metadata},
                )
            )

        return filtered

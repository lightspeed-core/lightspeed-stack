"""Shared test helpers for inference providers."""

from typing import Any, Optional

from pydantic_ai.embeddings import EmbeddingModel, TestEmbeddingModel
from pydantic_ai.models import Model
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers import Provider
from sentence_transformers import CrossEncoder

from models.config import InferenceProviderEntryBase
from providers.inference.base import InferenceProvider
from providers.inference.catalog import CatalogModel, DiscoveredModel
from providers.inference.types import ModelType


class FakeInferenceProvider(
    InferenceProvider[InferenceProviderEntryBase, Provider[Any]]
):
    """Minimal concrete provider for testing shared behavior."""

    def _build_provider(self) -> Optional[Provider[Any]]:
        """No PydanticAI provider is required for unit tests."""
        return None

    async def _discover_models(self) -> list[DiscoveredModel]:
        """Return no discovered models; tests use skip_model_discovery."""
        return []

    def _create_llm(self, model: CatalogModel) -> Model:
        """Return a PydanticAI test chat model tagged with the catalog name."""
        return TestModel(model_name=model.name)

    def _create_embedding(self, model: CatalogModel) -> EmbeddingModel:
        """Return a PydanticAI test embedding model."""
        return TestEmbeddingModel()

    def _create_rerank(self, model: CatalogModel) -> CrossEncoder:
        """Return a CrossEncoder stub without loading weights."""
        return object.__new__(CrossEncoder)

    def _infer_model_type(
        self,
        provider_model_id: str,
        **kwargs: Any,
    ) -> Optional[ModelType]:
        """Return llm for unknown model IDs."""
        return "llm"


def make_catalog_models() -> list[CatalogModel]:
    """Create a representative catalog covering all model types."""
    return [
        CatalogModel(
            name="chat-model",
            provider_model_id="provider-chat-model",
            model_type="llm",
            metadata={"tags": ["chat"]},
        ),
        CatalogModel(
            name="embedding-model",
            provider_model_id="provider-embedding-model",
            model_type="embedding",
            metadata={},
        ),
        CatalogModel(
            name="rerank-model",
            provider_model_id="provider-rerank-model",
            model_type="rerank",
            metadata={},
        ),
    ]


def make_fake_provider(
    provider_id: str = "test-provider",
    models: Optional[list[CatalogModel]] = None,
) -> FakeInferenceProvider:
    """Create a fake provider with a preloaded catalog.

    Args:
        provider_id: Local identifier assigned to the provider.
        models: Catalog models to preload. Uses the default representative
            catalog when omitted.

    """
    entry = InferenceProviderEntryBase(
        id=provider_id,
    )  # pyright: ignore[reportCallIssue]
    provider = FakeInferenceProvider(entry)
    provider._models = (  # pylint: disable=protected-access
        models if models is not None else make_catalog_models()
    )
    return provider

"""Vertex AI runtime inference provider backed by Pydantic AI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic_ai.embeddings import EmbeddingModel
from pydantic_ai.embeddings.google import GoogleEmbeddingModel
from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google_cloud import GoogleCloudProvider
from sentence_transformers import CrossEncoder

from models.config import VertexAIInferenceProviderEntry
from providers.inference.base import InferenceProvider
from providers.inference.catalog import CatalogModel, DiscoveredModel
from providers.inference.errors import ModelTypeNotSupportedError
from providers.inference.model_type_inference import (
    infer_model_type_from_pai_known_names,
)

if TYPE_CHECKING:
    from providers.inference.types import ModelType


class VertexAIInferenceProvider(
    InferenceProvider[VertexAIInferenceProviderEntry, GoogleCloudProvider]
):
    """Inference provider for Google Vertex AI (Google Cloud) APIs."""

    def _build_provider(self) -> GoogleCloudProvider:
        """Build the Pydantic AI Google Cloud provider from configuration.

        Uses Application Default Credentials. Set GOOGLE_APPLICATION_CREDENTIALS
        when a credentials file is required.

        Returns:
            A Pydantic AI Google Cloud provider using the configured project and
            location.

        """
        config = self._entry.config
        return GoogleCloudProvider(project=config.project, location=config.location)

    async def _discover_models(self) -> list[DiscoveredModel]:
        """List models from the Vertex AI model catalog.

        Keeps each catalog resource name as the provider model id so Model Garden
        publisher paths remain usable for inference.

        Returns:
            Discovered models with inferred types, before allow-list filtering.

        """
        discovered: list[DiscoveredModel] = []
        pager = await self._get_provider.client.aio.models.list()
        async for model in pager:
            if not model.name:
                continue
            discovered.append(
                DiscoveredModel(
                    provider_model_id=model.name,
                    model_type=self._infer_model_type(
                        model.name,
                        supported_actions=model.supported_actions,
                    ),
                )
            )
        return discovered

    def _create_llm(self, model: CatalogModel) -> Model:
        """Create a Google chat model for a catalog entry.

        Args:
            model: Catalog entry describing the LLM to instantiate.

        Returns:
            A Pydantic AI Google model bound to this provider.

        """
        return GoogleModel(
            model.provider_model_id,
            provider=self._get_provider,
        )

    def _create_embedding(self, model: CatalogModel) -> EmbeddingModel:
        """Create a Google embedding model for a catalog entry.

        Args:
            model: Catalog entry describing the embedding model to instantiate.

        Returns:
            A Pydantic AI Google embedding model bound to this provider.

        """
        return GoogleEmbeddingModel(
            model.provider_model_id,
            provider=self._get_provider,
        )

    def _create_rerank(self, model: CatalogModel) -> CrossEncoder:
        """Reject rerank requests; this provider has no rerank API.

        Args:
            model: Catalog entry that requested rerank support.

        Raises:
            ModelTypeNotSupportedError: Always, because rerank is unsupported.

        """
        _ = model
        raise ModelTypeNotSupportedError("rerank", self.provider_id)

    def _infer_model_type(
        self,
        provider_model_id: str,
        **kwargs: Any,
    ) -> ModelType:
        """Infer model type from known PAI names, then Vertex supported actions.

        Args:
            provider_model_id: Model id from Vertex or from an allow-list entry.
            **kwargs: Optional supported_actions from catalog discovery.

        Returns:
            embedding when the model id is a known embedding model or
            supported_actions includes embedContent; otherwise llm.

        """
        short_id = provider_model_id.rsplit("/", 1)[-1]
        if known := infer_model_type_from_pai_known_names(short_id):
            return known

        supported_actions = kwargs.get("supported_actions") or []
        if "embedContent" in supported_actions:
            return "embedding"
        return "llm"

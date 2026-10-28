"""OpenAI runtime inference provider backed by Pydantic AI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic_ai.embeddings import EmbeddingModel
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from sentence_transformers import CrossEncoder

from models.config import OpenAIInferenceProviderEntry
from providers.inference.base import InferenceProvider
from providers.inference.catalog import CatalogModel, DiscoveredModel
from providers.inference.errors import ModelTypeNotSupportedError
from providers.inference.model_type_inference import (
    infer_model_type_from_pai_known_names,
)

if TYPE_CHECKING:
    from providers.inference.types import ModelType


class OpenAIInferenceProvider(
    InferenceProvider[OpenAIInferenceProviderEntry, OpenAIProvider]
):
    """Inference provider for OpenAI HTTP APIs."""

    def _build_provider(self) -> OpenAIProvider:
        """Build the Pydantic AI OpenAI provider from configuration.

        Returns:
            A Pydantic AI OpenAI provider using the configured API key and
            base URL.

        """
        config = self._entry.config
        api_key = (
            config.api_key.get_secret_value() if config.api_key is not None else None
        )
        return OpenAIProvider(api_key=api_key, base_url=config.base_url)

    async def _discover_models(self) -> list[DiscoveredModel]:
        """List models from the OpenAI models endpoint.

        Returns:
            Discovered models with inferred types, before allow-list filtering.

        """
        response = await self._get_provider.client.models.list()
        return [
            DiscoveredModel(
                provider_model_id=model.id,
                model_type=self._infer_model_type(model.id),
            )
            for model in response.data
        ]

    def _create_llm(self, model: CatalogModel) -> Model:
        """Create a Responses API chat model for a catalog entry.

        Args:
            model: Catalog entry describing the LLM to instantiate.

        Returns:
            A Pydantic AI OpenAI Responses model bound to this provider.

        """
        return OpenAIResponsesModel(
            model.provider_model_id,
            provider=self._get_provider,
        )

    def _create_embedding(self, model: CatalogModel) -> EmbeddingModel:
        """Create an embedding model for a catalog entry.

        Args:
            model: Catalog entry describing the embedding model to instantiate.

        Returns:
            A Pydantic AI OpenAI embedding model bound to this provider.

        """
        return OpenAIEmbeddingModel(
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
        """Infer model type from Pydantic AI known LLM and embedding names.

        Args:
            provider_model_id: Model id from OpenAI or from an allow-list entry.
            **kwargs: Unused; accepted for base-class compatibility.

        Returns:
            embedding when the id is a known embedding model, otherwise llm.

        """
        _ = kwargs
        return infer_model_type_from_pai_known_names(provider_model_id) or "llm"

"""Azure OpenAI runtime inference provider backed by Pydantic AI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from azure.identity.aio import ClientSecretCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI
from pydantic_ai.embeddings import EmbeddingModel
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.azure import AzureProvider
from sentence_transformers import CrossEncoder

from configuration import configuration
from models.config import AzureInferenceProviderEntry
from providers.inference.base import InferenceProvider
from providers.inference.catalog import CatalogModel, DiscoveredModel
from providers.inference.errors import ModelTypeNotSupportedError
from providers.inference.model_type_inference import (
    infer_model_type_from_pai_known_names,
)

if TYPE_CHECKING:
    from providers.inference.types import ModelType


class AzureInferenceProvider(
    InferenceProvider[AzureInferenceProviderEntry, AzureProvider]
):
    """Inference provider for Azure OpenAI HTTP APIs."""

    def _build_provider(self) -> AzureProvider:
        """Build the Pydantic AI Azure provider from an LCORE-owned client.

        Returns:
            A Pydantic AI Azure provider wrapping an ``AsyncAzureOpenAI``
            client configured with API-key or Entra ID authentication.

        """
        config = self._entry.config
        client_kwargs: dict[str, Any] = {
            "api_version": config.api_version,
        }
        if config.base_url is not None:
            client_kwargs["azure_endpoint"] = config.base_url

        if (entra_id := config.entra_id or configuration.azure_entra_id) is not None:
            credential = ClientSecretCredential(
                tenant_id=entra_id.tenant_id.get_secret_value(),
                client_id=entra_id.client_id.get_secret_value(),
                client_secret=entra_id.client_secret.get_secret_value(),
            )
            client_kwargs["azure_ad_token_provider"] = get_bearer_token_provider(
                credential,
                entra_id.scope,
            )
        else:
            client_kwargs["api_key"] = (
                config.api_key.get_secret_value()
                if config.api_key is not None
                else None
            )

        return AzureProvider(openai_client=AsyncAzureOpenAI(**client_kwargs))

    async def _discover_models(self) -> list[DiscoveredModel]:
        """List models from the Azure OpenAI models endpoint.

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
            provider_model_id: Model id from Azure OpenAI or from an allow-list
                entry.
            **kwargs: Unused; accepted for base-class compatibility.

        Returns:
            embedding when the id is a known embedding model, otherwise llm.

        """
        _ = kwargs
        return infer_model_type_from_pai_known_names(provider_model_id) or "llm"

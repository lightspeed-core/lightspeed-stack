"""WatsonX runtime inference provider backed by Pydantic AI."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional

from pydantic_ai.embeddings import EmbeddingModel
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from sentence_transformers import CrossEncoder

from models.config import WatsonxInferenceProviderEntry
from providers.inference.base import InferenceProvider
from providers.inference.catalog import CatalogModel, DiscoveredModel
from providers.inference.errors import ModelTypeNotSupportedError
from providers.inference.watsonx.pai_provider import WatsonxProvider
from providers.inference.watsonx.specs import FoundationModelSpecsResponse

if TYPE_CHECKING:
    from providers.inference.types import ModelType


class WatsonxInferenceProvider(
    InferenceProvider[WatsonxInferenceProviderEntry, WatsonxProvider]
):
    """Inference provider for IBM WatsonX OpenAI-compatible APIs."""

    def _build_provider(self) -> WatsonxProvider:
        """Build the Pydantic AI WatsonX provider from configuration.

        Returns:
            A WatsonxProvider using the configured credentials and base URL.

        """
        config = self._entry.config
        api_key = (
            config.api_key.get_secret_value() if config.api_key is not None else None
        )
        return WatsonxProvider(api_key=api_key, base_url=config.base_url)

    async def _discover_models(self) -> list[DiscoveredModel]:
        """Discover project chat and embedding models.

        Intersects the project models list with foundation model specs and
        keeps only models typed as chat or embedding.

        Returns:
            Discovered models before allow-list filtering.

        """
        project_id = self._entry.config.project_id
        pai = self._get_provider
        models_response, functions_by_id = await asyncio.gather(
            pai.client.models.list(
                extra_query={"project_id": project_id} if project_id else None,
            ),
            self._list_foundation_model_functions(),
        )

        discovered: list[DiscoveredModel] = []
        for model in models_response.data:
            model_type = self._infer_model_type(
                model.id,
                functions_by_id=functions_by_id,
            )
            if model_type is None:
                continue
            discovered.append(
                DiscoveredModel(
                    provider_model_id=model.id,
                    model_type=model_type,
                )
            )
        return discovered

    async def _list_foundation_model_functions(self) -> dict[str, frozenset[str]]:
        """Load foundation model function ids keyed by model id.

        Returns:
            Mapping of model id to advertised function ids such as text_chat
            or embedding.

        """
        payload = await self._get_provider.client.get(
            "/foundation_model_specs",
            cast_to=FoundationModelSpecsResponse,
        )
        return {
            resource.model_id: frozenset(function.id for function in resource.functions)
            for resource in payload.resources
        }

    def _create_llm(self, model: CatalogModel) -> Model:
        """Create a chat model for a catalog entry.

        Args:
            model: Catalog entry describing the LLM to instantiate.

        Returns:
            A Pydantic AI OpenAI chat model bound to this provider.

        """
        return OpenAIChatModel(
            model.provider_model_id,
            provider=self._get_provider,
            settings={
                "extra_body": {
                    "project_id": self._entry.config.project_id,
                },
            },
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
            settings={
                "extra_body": {
                    "project_id": self._entry.config.project_id,
                },
            },
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
    ) -> Optional[ModelType]:
        """Infer model type from foundation model function ids.

        Args:
            provider_model_id: Model id from WatsonX or an allow-list entry.
            **kwargs: Optional functions_by_id mapping from foundation specs.

        Returns:
            embedding or llm when supported, otherwise None.

        """
        functions_by_id: dict[str, frozenset[str]] = kwargs.get("functions_by_id") or {}
        model_functions = functions_by_id.get(provider_model_id)
        if model_functions is None:
            return None
        if "embedding" in model_functions:
            return "embedding"
        if "text_chat" in model_functions:
            return "llm"
        return None

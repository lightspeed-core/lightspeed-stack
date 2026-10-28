"""AWS Bedrock runtime inference provider backed by Pydantic AI."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any, Optional

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.session import Session
from botocore.tokens import FrozenAuthToken
from pydantic_ai.embeddings import EmbeddingModel
from pydantic_ai.embeddings.bedrock import BedrockEmbeddingModel
from pydantic_ai.models import Model
from pydantic_ai.models.bedrock import BedrockConverseModel
from pydantic_ai.providers.bedrock import BedrockProvider
from sentence_transformers import CrossEncoder

from models.config import BedrockInferenceProviderEntry
from providers.inference.base import InferenceProvider
from providers.inference.bedrock.specs import FoundationModelSummary
from providers.inference.catalog import CatalogModel, DiscoveredModel
from providers.inference.errors import ModelTypeNotSupportedError

if TYPE_CHECKING:
    from providers.inference.types import ModelType


class _BearerTokenSession(Session):
    """Botocore session that authenticates Bedrock with a bearer token."""

    def __init__(self, token: str) -> None:
        """Initialize with a Bedrock bearer token.

        Args:
            token: AWS Bedrock bearer token value.

        """
        super().__init__()
        self.token = token

    def get_auth_token(self, **_kwargs: Any) -> FrozenAuthToken:
        """Return the configured bearer token.

        Returns:
            Frozen auth token wrapping the configured bearer value.

        """
        return FrozenAuthToken(self.token)

    def get_credentials(self) -> None:  # type: ignore[override]
        """Return no SigV4 credentials; bearer auth is used instead.

        Returns:
            None, because this session does not use access-key credentials.

        """
        return


class BedrockInferenceProvider(
    InferenceProvider[BedrockInferenceProviderEntry, BedrockProvider]
):
    """Inference provider for AWS Bedrock foundation models."""

    def _build_provider(self) -> BedrockProvider:
        """Build the Pydantic AI Bedrock runtime provider from configuration.

        Returns:
            A Pydantic AI Bedrock provider using the configured region, optional
            profile, and optional bearer token.

        """
        config = self._entry.config
        api_key = (
            config.api_key.get_secret_value() if config.api_key is not None else None
        )
        return BedrockProvider(
            region_name=config.region,
            profile_name=config.profile_name,
            api_key=api_key,  # type: ignore[arg-type]
        )

    def _create_bedrock_client(self) -> BaseClient:
        """Build a Bedrock control-plane client from provider configuration.

        Returns:
            A Bedrock client for the configured region. Uses bearer auth when a
            non-empty token is configured or present in
            AWS_BEARER_TOKEN_BEDROCK; otherwise uses the standard AWS
            credential chain with the optional profile.

        """
        config = self._entry.config
        api_key = (
            config.api_key.get_secret_value()
            if config.api_key is not None
            else os.getenv("AWS_BEARER_TOKEN_BEDROCK")
        )
        session = boto3.Session(
            profile_name=config.profile_name,
            region_name=config.region,
            botocore_session=_BearerTokenSession(api_key) if api_key else None,
        )
        return session.client(
            "bedrock",
            config=Config(signature_version="bearer") if api_key else None,
        )

    async def _discover_models(self) -> list[DiscoveredModel]:
        """List regional foundation models and infer their types.

        Returns:
            Discovered models with inferred types, before allow-list filtering.
            Models without TEXT or EMBEDDING output modalities are omitted.

        """
        client = self._create_bedrock_client()
        response = await asyncio.to_thread(client.list_foundation_models)

        discovered: list[DiscoveredModel] = []
        for summary in response.get("modelSummaries", []):
            model = FoundationModelSummary.model_validate(summary)
            model_type = self._infer_model_type(
                model.model_id,
                output_modalities=model.output_modalities,
            )
            if model_type is None:
                continue
            discovered.append(
                DiscoveredModel(
                    provider_model_id=model.model_id,
                    model_type=model_type,
                )
            )
        return discovered

    def _create_llm(self, model: CatalogModel) -> Model:
        """Create a Converse chat model for a catalog entry.

        Args:
            model: Catalog entry describing the LLM to instantiate.

        Returns:
            A Pydantic AI Bedrock Converse model bound to this provider.

        """
        return BedrockConverseModel(
            model.provider_model_id,
            provider=self._get_provider,
        )

    def _create_embedding(self, model: CatalogModel) -> EmbeddingModel:
        """Create an embedding model for a catalog entry.

        Args:
            model: Catalog entry describing the embedding model to instantiate.

        Returns:
            A Pydantic AI Bedrock embedding model bound to this provider.

        """
        return BedrockEmbeddingModel(
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
    ) -> Optional[ModelType]:
        """Infer model type from Bedrock output modalities.

        Args:
            provider_model_id: Model id from Bedrock or from an allow-list entry.
            **kwargs: Optional output_modalities list from model summaries.

        Returns:
            embedding when modalities include EMBEDDING, llm when they include
            TEXT, otherwise None so discovery can skip the model.

        """
        _ = provider_model_id
        output_modalities = kwargs.get("output_modalities") or []
        if "EMBEDDING" in output_modalities:
            return "embedding"
        if "TEXT" in output_modalities:
            return "llm"
        return None

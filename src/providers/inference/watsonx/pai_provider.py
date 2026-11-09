"""Pydantic AI provider for IBM WatsonX OpenAI-compatible APIs."""

from __future__ import annotations

import os
from typing import Optional

import httpx
from openai import AsyncOpenAI
from pydantic_ai import ModelProfile
from pydantic_ai.exceptions import UserError
from pydantic_ai.profiles import merge_profile
from pydantic_ai.profiles.openai import (
    OpenAIJsonSchemaTransformer,
    OpenAIModelProfile,
    openai_model_profile,
)
from pydantic_ai.providers import Provider

from providers.inference.watsonx.auth import WatsonxIAMAuth

WATSONX_API_VERSION = "2023-10-25"
DEFAULT_WATSONX_BASE_URL = "https://us-south.ml.cloud.ibm.com"


class WatsonxProvider(Provider[AsyncOpenAI]):
    """Provider for IBM WatsonX using an OpenAI-compatible client."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        """Create a WatsonX provider from connection settings.

        Args:
            api_key: WatsonX API key. Falls back to the WATSONX_API_KEY
                environment variable.
            base_url: WatsonX host URL without the /ml/v1 suffix. Falls back
                to WATSONX_BASE_URL, then the us-south default.

        Raises:
            UserError: If the API key cannot be resolved.

        """
        api_key = api_key or os.getenv("WATSONX_API_KEY")
        if not api_key:
            raise UserError(
                "Must provide one of the `api_key` argument or the "
                "`WATSONX_API_KEY` environment variable"
            )

        resolved_base_url = (
            base_url or os.getenv("WATSONX_BASE_URL") or DEFAULT_WATSONX_BASE_URL
        )
        self._base_url = resolved_base_url.rstrip("/")
        # OpenAI 3 types http_client as httpx2 only; legacy httpx still works.
        self._client = AsyncOpenAI(
            api_key="unused",
            base_url=f"{self._base_url}/ml/v1",
            default_query={"version": WATSONX_API_VERSION},
            http_client=httpx.AsyncClient(auth=WatsonxIAMAuth(api_key)),  # type: ignore[arg-type]
        )

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "watsonx"

    @property
    def base_url(self) -> str:
        """Return the resolved WatsonX host URL, without the API path."""
        return self._base_url

    @property
    def client(self) -> AsyncOpenAI:
        """Return the OpenAI-compatible client."""
        return self._client

    @staticmethod
    def model_profile(model_name: str) -> Optional[ModelProfile]:
        """Return an OpenAI-compatible profile for a WatsonX model.

        Args:
            model_name: Provider model identifier.

        Returns:
            A merged OpenAI model profile suitable for chat models.

        """
        return merge_profile(
            OpenAIModelProfile(json_schema_transformer=OpenAIJsonSchemaTransformer),
            openai_model_profile(model_name),
        )

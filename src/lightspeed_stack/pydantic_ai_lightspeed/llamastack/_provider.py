"""Llama Stack provider implementation for Pydantic AI."""

from __future__ import annotations as _annotations

from typing import TYPE_CHECKING, Optional

import httpx
from ogx.core.library_client import AsyncOGXAsLibraryClient
from ogx.core.request_headers import parse_request_provider_data
from ogx_client import AsyncOgxClient
from openai import AsyncOpenAI
from pydantic_ai import ModelProfile
from pydantic_ai.models import create_async_http_client
from pydantic_ai.profiles.openai import openai_model_profile
from pydantic_ai.providers import Provider

from pydantic_ai_lightspeed.llamastack._transport import (
    OgxLibraryTransport,
    wrap_http_client_with_provider_data,
)

if TYPE_CHECKING:
    from ogx.core.library_client import (  # pylint: disable=reimported
        AsyncOGXAsLibraryClient,
    )

DEFAULT_BASE_URL = "http://localhost:8321/v1"


class OgxProvider(Provider[AsyncOpenAI]):
    """Provider for Llama Stack — connects to a Llama Stack server's OpenAI-compatible API.

    Supports two modes:

    1. **Server mode** — connect to a running Llama Stack server via HTTP
    2. **Library mode** — run Llama Stack in-process via ``AsyncOGXAsLibraryClient``
    """

    @property
    def name(self) -> str:
        """The provider name."""
        return "llama-stack"

    @property
    def base_url(self) -> str:
        """The base URL for the provider API."""
        return str(self._client.base_url)

    @property
    def client(self) -> AsyncOpenAI:
        """The OpenAI-compatible client for the provider."""
        return self._client

    @staticmethod
    def model_profile(model_name: str) -> Optional[ModelProfile]:
        """Return the model profile for the named model, if available."""
        return openai_model_profile(model_name)

    @staticmethod
    def from_ogx_client(
        client: AsyncOgxClient | AsyncOGXAsLibraryClient,
    ) -> OgxProvider:
        """Create a ``OgxProvider`` from a Llama Stack client.

        For an ``AsyncOGXAsLibraryClient``, delegates to library mode.
        For an ``AsyncOgxClient``, extracts the base URL, API key, and
        underlying HTTP client to create a server-mode provider.

        Args:
            client: A Llama Stack client (server or library variant).

        Returns:
            Configured ``OgxProvider`` instance.
        """
        if isinstance(client, AsyncOGXAsLibraryClient):
            return OgxProvider(library_client=client)
        api_key = client.api_key or "not-needed"
        base = str(client.base_url).rstrip("/")
        base_url = base if base.endswith("/v1") else f"{base}/v1"
        raw_headers = client.default_headers
        default_headers = {
            str(key): str(value)
            for key, value in raw_headers.items()
            if isinstance(value, str)
        }
        provider_data = parse_request_provider_data(default_headers)
        http_client = client._client  # pylint: disable=protected-access
        http_client = wrap_http_client_with_provider_data(http_client, provider_data)
        return OgxProvider(
            base_url=base_url,
            api_key=api_key,
            http_client=http_client,
        )

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        library_client: Optional[AsyncOGXAsLibraryClient] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        """Create a new Llama Stack provider.

        Args:
            base_url: The base URL for the Llama Stack server (OpenAI-compatible endpoint).
                Defaults to ``http://localhost:8321/v1``.
                Must be ``None`` when ``library_client`` is provided.
            api_key: The API key for authentication. Defaults to ``'not-needed'`` since
                local Llama Stack servers typically don't require one.
                Must be ``None`` when ``library_client`` is provided.
            library_client: An initialized ``AsyncOGXAsLibraryClient`` for library mode.
                When provided, requests are dispatched in-process (no server needed).
                Mutually exclusive with ``base_url``, ``api_key``, and ``http_client``.
            http_client: An existing ``httpx.AsyncClient`` to use for making HTTP requests.
                Must be ``None`` when ``library_client`` is provided.
        """
        if library_client is not None:
            if base_url is not None:
                raise ValueError("Cannot provide both `library_client` and `base_url`")
            if api_key is not None:
                raise ValueError("Cannot provide both `library_client` and `api_key`")
            if http_client is not None:
                raise ValueError(
                    "Cannot provide both `library_client` and `http_client`"
                )

            self._library_client = library_client
            transport = OgxLibraryTransport(library_client)
            lib_http_client = httpx.AsyncClient(
                transport=transport,
                base_url="http://llama-stack-library",
                timeout=httpx.Timeout(None),
            )
            self._client = AsyncOpenAI(
                http_client=lib_http_client,
                base_url="http://llama-stack-library/v1",
                api_key="not-needed",
            )
        else:
            base_url = base_url or DEFAULT_BASE_URL
            api_key = api_key or "not-needed"

            self._client = AsyncOpenAI(
                base_url=base_url,
                api_key=api_key,
                http_client=http_client or create_async_http_client(),
            )

    def __repr__(self) -> str:
        """Return a string representation of the provider."""
        return f"OgxProvider(name={self.name!r}, base_url={self.base_url!r})"

    def _set_http_client(self, http_client: httpx.AsyncClient) -> None:
        """Inject an httpx.AsyncClient into the underlying OpenAI client.

        Replaces the internal HTTP transport by assigning directly to the
        protected ``self._client._client`` attribute of the AsyncOpenAI instance.

        Args:
            http_client: The async HTTP client to use for subsequent requests.
        """
        self._client._client = http_client  # pyright: ignore[reportPrivateUsage]  # pylint: disable=protected-access

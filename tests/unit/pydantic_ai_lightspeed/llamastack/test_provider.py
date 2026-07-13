"""Unit tests for pydantic_ai_lightspeed.llamastack._provider module."""

# pylint: disable=protected-access

import httpx
import pytest
from llama_stack.core.library_client import AsyncLlamaStackAsLibraryClient
from llama_stack_client import AsyncLlamaStackClient
from openai import AsyncOpenAI
from pytest_mock import MockerFixture

from pydantic_ai_lightspeed.llamastack._provider import (
    DEFAULT_BASE_URL,
    LlamaStackProvider,
)
from pydantic_ai_lightspeed.llamastack._transport import LlamaStackServerTransport


class TestLlamaStackProviderProperties:
    """Tests for LlamaStackProvider basic properties."""

    def test_name(self) -> None:
        """Test that the provider name is 'llama-stack'."""
        provider = LlamaStackProvider()
        assert provider.name == "llama-stack"

    def test_base_url_default(self) -> None:
        """Test that the default base URL matches the expected default."""
        provider = LlamaStackProvider()
        assert DEFAULT_BASE_URL in provider.base_url

    def test_client_returns_async_openai(self) -> None:
        """Test that the client property returns an AsyncOpenAI instance."""
        provider = LlamaStackProvider()
        assert isinstance(provider.client, AsyncOpenAI)

    def test_repr(self) -> None:
        """Test the string representation of the provider."""
        provider = LlamaStackProvider()
        result = repr(provider)
        assert "LlamaStackProvider" in result
        assert "llama-stack" in result

    def test_model_profile_known_model(self) -> None:
        """Test model_profile returns a profile for a known OpenAI model."""
        profile = LlamaStackProvider.model_profile("gpt-4o")
        assert profile is not None

    def test_model_profile_unknown_model(self) -> None:
        """Test model_profile returns a default profile for an unrecognized model."""
        profile = LlamaStackProvider.model_profile("totally-unknown-model-xyz")
        assert profile is not None


class TestLlamaStackProviderServerMode:
    """Tests for LlamaStackProvider server mode initialization."""

    def test_explicit_base_url(self) -> None:
        """Test that an explicit base_url is used."""
        provider = LlamaStackProvider(base_url="http://my-server:9999/v1")
        assert "my-server:9999" in provider.base_url

    def test_explicit_api_key(self) -> None:
        """Test that an explicit api_key is used."""
        provider = LlamaStackProvider(api_key="my-secret-key")
        assert provider.client.api_key == "my-secret-key"

    def test_default_api_key_is_not_needed(self) -> None:
        """Test that the default API key is 'not-needed'."""
        provider = LlamaStackProvider()
        assert provider.client.api_key == "not-needed"

    def test_custom_http_client(self, mocker: MockerFixture) -> None:
        """Test that a provided http_client is wired into the provider."""
        custom_client = mocker.Mock(spec=httpx.AsyncClient)
        provider = LlamaStackProvider(http_client=custom_client)
        assert provider._client._client is custom_client


class TestLlamaStackProviderLibraryMode:
    """Tests for LlamaStackProvider library mode initialization."""

    def test_library_client_creates_transport(self, mocker: MockerFixture) -> None:
        """Test that providing a library_client sets up the transport-based client."""
        mock_lib_client = mocker.Mock()
        mock_lib_client.provider_data = None

        provider = LlamaStackProvider(library_client=mock_lib_client)

        assert provider._library_client is mock_lib_client
        assert "llama-stack-library" in provider.base_url

    def test_library_client_api_key_is_not_needed(self, mocker: MockerFixture) -> None:
        """Test that library mode sets the API key to 'not-needed'."""
        mock_lib_client = mocker.Mock()
        mock_lib_client.provider_data = None

        provider = LlamaStackProvider(library_client=mock_lib_client)

        assert provider.client.api_key == "not-needed"


class TestLlamaStackProviderMutualExclusion:
    """Tests for mutual exclusion between library_client and server mode options."""

    def test_library_client_and_base_url_raises(self, mocker: MockerFixture) -> None:
        """Test that providing both library_client and base_url raises ValueError."""
        mock_lib_client = mocker.Mock()
        mock_lib_client.provider_data = None

        with pytest.raises(
            ValueError,
            match="Cannot provide both `library_client` and `base_url`",
        ):
            LlamaStackProvider(
                library_client=mock_lib_client,
                base_url="http://localhost:8321/v1",
            )

    def test_library_client_and_api_key_raises(self, mocker: MockerFixture) -> None:
        """Test that providing both library_client and api_key raises ValueError."""
        mock_lib_client = mocker.Mock()
        mock_lib_client.provider_data = None

        with pytest.raises(
            ValueError,
            match="Cannot provide both `library_client` and `api_key`",
        ):
            LlamaStackProvider(
                library_client=mock_lib_client,
                api_key="my-key",
            )

    def test_library_client_and_http_client_raises(self, mocker: MockerFixture) -> None:
        """Test that providing both library_client and http_client raises ValueError."""
        mock_lib_client = mocker.Mock()
        mock_lib_client.provider_data = None

        with pytest.raises(
            ValueError,
            match="Cannot provide both `library_client` and `http_client`",
        ):
            LlamaStackProvider(
                library_client=mock_lib_client,
                http_client=mocker.Mock(spec=httpx.AsyncClient),
            )


class TestFromLlamaStackClient:
    """Tests for LlamaStackProvider.from_llama_stack_client."""

    def test_library_client_dispatches_to_library_mode(
        self, mocker: MockerFixture
    ) -> None:
        """Test that an AsyncLlamaStackAsLibraryClient creates a library-mode provider."""
        mock_lib_client = mocker.Mock(spec=AsyncLlamaStackAsLibraryClient)
        mock_lib_client.provider_data = None

        provider = LlamaStackProvider.from_llama_stack_client(mock_lib_client)

        assert provider._library_client is mock_lib_client
        assert "llama-stack-library" in provider.base_url

    def test_server_client_extracts_base_url_with_v1(
        self, mocker: MockerFixture
    ) -> None:
        """Test that a server client whose base_url already ends with /v1 is used as-is."""
        mock_client = mocker.Mock(spec=AsyncLlamaStackClient)
        mock_client.base_url = "http://my-server:8321/v1"
        mock_client.api_key = "test-key"
        mock_client._client = mocker.Mock(spec=httpx.AsyncClient)
        mock_client.default_headers = {}

        provider = LlamaStackProvider.from_llama_stack_client(mock_client)

        assert "my-server:8321/v1" in provider.base_url
        assert provider.base_url.count("/v1") == 1

    def test_server_client_appends_v1_when_missing(self, mocker: MockerFixture) -> None:
        """Test that /v1 is appended when the server client's base_url lacks it."""
        mock_client = mocker.Mock(spec=AsyncLlamaStackClient)
        mock_client.base_url = "http://my-server:8321"
        mock_client.api_key = "test-key"
        mock_client._client = mocker.Mock(spec=httpx.AsyncClient)
        mock_client.default_headers = {}

        provider = LlamaStackProvider.from_llama_stack_client(mock_client)

        assert provider.base_url.rstrip("/").endswith("/v1")

    def test_server_client_strips_trailing_slash_before_appending_v1(
        self, mocker: MockerFixture
    ) -> None:
        """Test that a trailing slash is stripped before appending /v1."""
        mock_client = mocker.Mock(spec=AsyncLlamaStackClient)
        mock_client.base_url = "http://my-server:8321/"
        mock_client.api_key = "test-key"
        mock_client._client = mocker.Mock(spec=httpx.AsyncClient)
        mock_client.default_headers = {}

        provider = LlamaStackProvider.from_llama_stack_client(mock_client)

        assert "//v1" not in provider.base_url
        assert provider.base_url.rstrip("/").endswith("/v1")

    def test_server_client_uses_provided_api_key(self, mocker: MockerFixture) -> None:
        """Test that the server client's api_key is forwarded to the provider."""
        mock_client = mocker.Mock(spec=AsyncLlamaStackClient)
        mock_client.base_url = "http://my-server:8321/v1"
        mock_client.api_key = "my-secret"
        mock_client._client = mocker.Mock(spec=httpx.AsyncClient)
        mock_client.default_headers = {}

        provider = LlamaStackProvider.from_llama_stack_client(mock_client)

        assert provider.client.api_key == "my-secret"

    def test_server_client_defaults_api_key_when_none(
        self, mocker: MockerFixture
    ) -> None:
        """Test that a None api_key falls back to 'not-needed'."""
        mock_client = mocker.Mock(spec=AsyncLlamaStackClient)
        mock_client.base_url = "http://my-server:8321/v1"
        mock_client.api_key = None
        mock_client._client = mocker.Mock(spec=httpx.AsyncClient)
        mock_client.default_headers = {}

        provider = LlamaStackProvider.from_llama_stack_client(mock_client)

        assert provider.client.api_key == "not-needed"

    def test_server_client_passes_http_client(self, mocker: MockerFixture) -> None:
        """Test that the server client's internal httpx client is reused when no provider data."""
        mock_client = mocker.Mock(spec=AsyncLlamaStackClient)
        mock_client.base_url = "http://my-server:8321/v1"
        mock_client.api_key = "test-key"
        inner_http = mocker.Mock(spec=httpx.AsyncClient)
        mock_client._client = inner_http
        mock_client.default_headers = {}

        provider = LlamaStackProvider.from_llama_stack_client(mock_client)

        assert provider._client._client is inner_http

    def test_server_client_wraps_transport_with_provider_data(
        self, mocker: MockerFixture
    ) -> None:
        """Test provider data from default_headers is forwarded in server mode."""
        mock_client = mocker.Mock(spec=AsyncLlamaStackClient)
        mock_client.base_url = "http://my-server:8321/v1"
        mock_client.api_key = "test-key"
        inner_http = httpx.AsyncClient()
        mock_client._client = inner_http
        mock_client.default_headers = {
            "X-LlamaStack-Provider-Data": '{"azure_api_key": "token"}'
        }

        provider = LlamaStackProvider.from_llama_stack_client(mock_client)

        assert isinstance(
            provider._client._client._transport,  # pylint: disable=protected-access
            LlamaStackServerTransport,
        )


class TestSetHttpClient:  # pylint: disable=too-few-public-methods
    """Tests for LlamaStackProvider._set_http_client."""

    def test_replaces_internal_http_client(self, mocker: MockerFixture) -> None:
        """Test that _set_http_client replaces the underlying httpx client."""
        provider = LlamaStackProvider()
        new_client = mocker.Mock(spec=httpx.AsyncClient)

        provider._set_http_client(new_client)

        assert provider._client._client is new_client

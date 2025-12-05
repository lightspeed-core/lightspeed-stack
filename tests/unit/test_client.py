"""Unit tests for functions defined in src/client.py."""

import ssl
from unittest.mock import patch, MagicMock

import pytest

from client import AsyncLlamaStackClientHolder
from models.config import LlamaStackConfiguration, TLSSecurityProfile


def test_async_client_get_client_method() -> None:
    """Test how get_client method works for uninitialized client."""
    client = AsyncLlamaStackClientHolder()

    with pytest.raises(
        RuntimeError,
        match=(
            "AsyncLlamaStackClient has not been initialised. "
            "Ensure 'load\\(..\\)' has been called."
        ),
    ):
        client.get_client()


@pytest.mark.asyncio
async def test_get_async_llama_stack_library_client() -> None:
    """Test the initialization of asynchronous Llama Stack client in library mode."""
    cfg = LlamaStackConfiguration(
        url=None,
        api_key=None,
        use_as_library_client=True,
        library_client_config_path="./tests/configuration/minimal-stack.yaml",
    )
    client = AsyncLlamaStackClientHolder()
    await client.load(cfg)
    assert client is not None

    async with client.get_client() as ls_client:
        assert ls_client is not None
        assert not ls_client.is_closed()
        await ls_client.close()
        assert ls_client.is_closed()


async def test_get_async_llama_stack_remote_client() -> None:
    """Test the initialization of asynchronous Llama Stack client in server mode."""
    cfg = LlamaStackConfiguration(
        url="http://localhost:8321",
        api_key=None,
        use_as_library_client=False,
        library_client_config_path="./tests/configuration/minimal-stack.yaml",
    )
    client = AsyncLlamaStackClientHolder()
    await client.load(cfg)
    assert client is not None

    ls_client = client.get_client()
    assert ls_client is not None


async def test_get_async_llama_stack_wrong_configuration() -> None:
    """Test if configuration is checked before Llama Stack is initialized."""
    cfg = LlamaStackConfiguration(
        url=None,
        api_key=None,
        use_as_library_client=True,
        library_client_config_path="./tests/configuration/minimal-stack.yaml",
    )
    cfg.library_client_config_path = None
    with pytest.raises(
        Exception,
        match="Configuration problem: library_client_config_path option is not set",
    ):
        client = AsyncLlamaStackClientHolder()
        await client.load(cfg)


class TestConstructHttpxClient:
    """Tests for _construct_httpx_client method."""

    def test_construct_httpx_client_no_profile(self) -> None:
        """Test that None is returned when no TLS profile is set."""
        holder = AsyncLlamaStackClientHolder()
        result = holder._construct_httpx_client(None)
        assert result is None

    def test_construct_httpx_client_profile_type_none(self) -> None:
        """Test that None is returned when profile_type is None."""
        holder = AsyncLlamaStackClientHolder()
        profile = TLSSecurityProfile()
        result = holder._construct_httpx_client(profile)
        assert result is None

    def test_construct_httpx_client_with_modern_profile(self) -> None:
        """Test that httpx client is created with ModernType profile."""
        holder = AsyncLlamaStackClientHolder()
        profile = TLSSecurityProfile(
            profile_type="ModernType",
            min_tls_version="VersionTLS13",
        )
        result = holder._construct_httpx_client(profile)
        assert result is not None

    def test_construct_httpx_client_with_custom_ciphers(self) -> None:
        """Test that httpx client is created with custom ciphers."""
        holder = AsyncLlamaStackClientHolder()
        profile = TLSSecurityProfile(
            profile_type="Custom",
            min_tls_version="VersionTLS12",
            ciphers=["TLS_AES_128_GCM_SHA256", "TLS_AES_256_GCM_SHA384"],
        )
        result = holder._construct_httpx_client(profile)
        assert result is not None

    @patch("client.ssl.create_default_context")
    def test_ssl_context_minimum_version_set(self, mock_create_context: MagicMock) -> None:
        """Test that SSL context minimum version is set correctly."""
        mock_context = MagicMock()
        mock_create_context.return_value = mock_context

        holder = AsyncLlamaStackClientHolder()
        profile = TLSSecurityProfile(
            profile_type="ModernType",
            min_tls_version="VersionTLS13",
        )
        holder._construct_httpx_client(profile)

        mock_create_context.assert_called_once()
        assert mock_context.minimum_version == ssl.TLSVersion.TLSv1_3

    @patch("client.ssl.create_default_context")
    def test_ssl_context_ciphers_set(self, mock_create_context: MagicMock) -> None:
        """Test that SSL context ciphers are set correctly."""
        mock_context = MagicMock()
        mock_create_context.return_value = mock_context

        holder = AsyncLlamaStackClientHolder()
        profile = TLSSecurityProfile(
            profile_type="Custom",
            ciphers=["CIPHER1", "CIPHER2"],
        )
        holder._construct_httpx_client(profile)

        mock_context.set_ciphers.assert_called_once_with("CIPHER1:CIPHER2")


async def test_get_async_llama_stack_remote_client_with_tls() -> None:
    """Test initialization of Llama Stack client with TLS profile."""
    tls_profile = TLSSecurityProfile(
        profile_type="ModernType",
        min_tls_version="VersionTLS13",
    )
    cfg = LlamaStackConfiguration(
        url="http://localhost:8321",
        api_key=None,
        use_as_library_client=False,
        library_client_config_path="./tests/configuration/minimal-stack.yaml",
        tls_security_profile=tls_profile,
    )
    client = AsyncLlamaStackClientHolder()
    await client.load(cfg)
    assert client is not None

    ls_client = client.get_client()
    assert ls_client is not None

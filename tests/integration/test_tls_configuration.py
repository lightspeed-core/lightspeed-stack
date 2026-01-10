"""Integration tests for TLS security profile configuration."""

import ssl
from unittest.mock import patch, MagicMock

import pytest

from configuration import AppConfig
from client import AsyncLlamaStackClientHolder


@pytest.fixture(name="tls_configuration_filename")
def tls_configuration_filename_fixture() -> str:
    """Retrieve TLS configuration file name for integration tests."""
    return "tests/configuration/lightspeed-stack-tls.yaml"


def test_loading_tls_configuration(tls_configuration_filename: str) -> None:
    """Test loading configuration with TLS security profile."""
    cfg = AppConfig()
    cfg.load_configuration(tls_configuration_filename)

    # check if configuration is loaded
    assert cfg is not None
    assert cfg.configuration is not None

    # check 'llama_stack' section
    ls_config = cfg.llama_stack_configuration
    assert ls_config.url == "https://localhost:8321"
    assert ls_config.use_as_library_client is False

    # check TLS security profile
    tls_profile = ls_config.tls_security_profile
    assert tls_profile is not None
    assert tls_profile.profile_type == "ModernType"
    assert tls_profile.min_tls_version == "VersionTLS13"
    assert tls_profile.ciphers == [
        "TLS_AES_128_GCM_SHA256",
        "TLS_AES_256_GCM_SHA384",
    ]


def test_tls_configuration_defaults(tls_configuration_filename: str) -> None:
    """Test that TLS configuration has correct default values."""
    cfg = AppConfig()
    cfg.load_configuration(tls_configuration_filename)

    tls_profile = cfg.llama_stack_configuration.tls_security_profile
    assert tls_profile is not None

    # These should be None/False by default when not specified
    assert tls_profile.ca_cert_path is None
    assert tls_profile.skip_tls_verification is False


@pytest.mark.asyncio
async def test_client_construction_with_tls_profile(
    tls_configuration_filename: str,
) -> None:
    """Test that AsyncLlamaStackClientHolder constructs client with TLS settings."""
    cfg = AppConfig()
    cfg.load_configuration(tls_configuration_filename)

    holder = AsyncLlamaStackClientHolder()

    # Mock httpx.AsyncClient to capture the SSL context
    with patch("client.httpx.AsyncClient") as mock_async_client:
        with patch("client.AsyncLlamaStackClient") as mock_llama_client:
            mock_async_client.return_value = MagicMock()
            mock_llama_client.return_value = MagicMock()

            await holder.load(cfg.llama_stack_configuration)

            # Verify httpx.AsyncClient was called with an SSL context
            mock_async_client.assert_called_once()
            call_kwargs = mock_async_client.call_args.kwargs
            verify_arg = call_kwargs.get("verify")

            # Should be an SSL context, not a boolean
            assert isinstance(verify_arg, ssl.SSLContext)

            # Verify minimum TLS version is set to TLS 1.3
            assert verify_arg.minimum_version == ssl.TLSVersion.TLSv1_3

            # Verify AsyncLlamaStackClient was called with the custom http_client
            mock_llama_client.assert_called_once()
            llama_call_kwargs = mock_llama_client.call_args.kwargs
            assert "http_client" in llama_call_kwargs
            assert llama_call_kwargs["http_client"] is not None


@pytest.mark.asyncio
async def test_client_construction_without_tls_profile() -> None:
    """Test that client is constructed normally without TLS profile."""
    from models.config import LlamaStackConfiguration

    cfg = LlamaStackConfiguration(
        url="http://localhost:8321",
        use_as_library_client=False,
        tls_security_profile=None,
    )

    holder = AsyncLlamaStackClientHolder()

    with patch("client.httpx.AsyncClient") as mock_async_client:
        with patch("client.AsyncLlamaStackClient") as mock_llama_client:
            mock_llama_client.return_value = MagicMock()

            await holder.load(cfg)

            # httpx.AsyncClient should NOT be called when no TLS profile
            mock_async_client.assert_not_called()

            # AsyncLlamaStackClient should be called with http_client=None
            mock_llama_client.assert_called_once()
            llama_call_kwargs = mock_llama_client.call_args.kwargs
            assert llama_call_kwargs.get("http_client") is None


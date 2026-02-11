"""Unit tests for LlamaStackConfiguration model."""

import pytest
from pydantic import ValidationError

from utils.checks import InvalidConfigurationError

from models.config import LlamaStackConfiguration


def test_llama_stack_configuration_constructor() -> None:
    """
    Verify that the LlamaStackConfiguration constructor accepts
    valid combinations of parameters and creates instances
    successfully.
    """
    llama_stack_configuration = LlamaStackConfiguration(
        use_as_library_client=True,
        library_client_config_path="tests/configuration/run.yaml",
        url=None,
        api_key=None,
        timeout=60,
    )
    assert llama_stack_configuration is not None

    llama_stack_configuration = LlamaStackConfiguration(
        use_as_library_client=False,
        url="http://localhost",
        library_client_config_path=None,
        api_key=None,
        timeout=60,
    )
    assert llama_stack_configuration is not None

    llama_stack_configuration = LlamaStackConfiguration(
        url="http://localhost"
    )  # pyright: ignore[reportCallIssue]
    assert llama_stack_configuration is not None

    llama_stack_configuration = LlamaStackConfiguration(
        use_as_library_client=False, url="http://localhost", api_key="foo"
    )  # pyright: ignore[reportCallIssue]
    assert llama_stack_configuration is not None


def test_llama_stack_configuration_no_run_yaml() -> None:
    """
    Verify that constructing a LlamaStackConfiguration with a
    non-existent or invalid library_client_config_path raises
    InvalidConfigurationError.
    """
    with pytest.raises(
        InvalidConfigurationError,
        match="Llama Stack configuration file 'not a file' is not a file",
    ):
        LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="not a file",
        )  # pyright: ignore[reportCallIssue]


def test_llama_stack_wrong_configuration_constructor_no_url() -> None:
    """
    Verify that constructing a LlamaStackConfiguration without
    specifying either a URL or enabling library client mode raises
    a ValueError.
    """
    with pytest.raises(
        ValueError,
        match="Llama stack URL is not specified and library client mode is not specified",
    ):
        LlamaStackConfiguration()  # pyright: ignore[reportCallIssue]


def test_llama_stack_wrong_configuration_constructor_library_mode_off() -> None:
    """Test the LlamaStackConfiguration constructor."""
    with pytest.raises(
        ValueError,
        match="Llama stack URL is not specified and library client mode is not enabled",
    ):
        LlamaStackConfiguration(
            use_as_library_client=False
        )  # pyright: ignore[reportCallIssue]


def test_llama_stack_wrong_configuration_no_config_file() -> None:
    """Test the LlamaStackConfiguration constructor."""
    m = "Llama stack library client mode is enabled but a configuration file path is not specified"
    with pytest.raises(ValueError, match=m):
        LlamaStackConfiguration(
            use_as_library_client=True
        )  # pyright: ignore[reportCallIssue]


def test_llama_stack_configuration_valid_http_url() -> None:
    """Test that valid HTTP URLs are accepted."""
    config = LlamaStackConfiguration(
        url="http://localhost:8321"
    )  # pyright: ignore[reportCallIssue]
    assert config is not None
    assert str(config.url) == "http://localhost:8321/"


def test_llama_stack_configuration_valid_https_url() -> None:
    """Test that valid HTTPS URLs are accepted."""
    config = LlamaStackConfiguration(
        url="https://llama-stack.example.com:8321"
    )  # pyright: ignore[reportCallIssue]
    assert config is not None
    assert str(config.url) == "https://llama-stack.example.com:8321/"


def test_llama_stack_configuration_malformed_url_rejected() -> None:
    """Test that malformed URLs are rejected with a ValidationError."""
    with pytest.raises(ValidationError, match="Input should be a valid URL"):
        LlamaStackConfiguration(
            url="not-a-valid-url"
        )  # pyright: ignore[reportCallIssue]


def test_llama_stack_configuration_invalid_scheme_rejected() -> None:
    """Test that URLs without http/https scheme are rejected."""
    with pytest.raises(ValidationError, match="URL scheme should be 'http' or 'https'"):
        LlamaStackConfiguration(
            url="ftp://localhost:8321"
        )  # pyright: ignore[reportCallIssue]

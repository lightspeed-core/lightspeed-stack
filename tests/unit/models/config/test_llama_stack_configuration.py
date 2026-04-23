"""Unit tests for LlamaStackConfiguration model."""

import pytest
from pydantic import AnyHttpUrl, ValidationError

from models.config import LlamaStackConfiguration
from utils.checks import InvalidConfigurationError


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
        url=AnyHttpUrl("http://localhost"),
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
    """Test the LlamaStackConfiguration constructor.

    Verify that enabling library-client mode without providing a configuration
    file path or unified config raises a ValueError.
    """
    m = (
        "Llama stack library client mode is enabled but neither `config` "
        "\\(unified\\) nor `library_client_config_path` \\(legacy\\) is specified"
    )
    with pytest.raises(ValueError, match=m):
        LlamaStackConfiguration(
            use_as_library_client=True
        )  # pyright: ignore[reportCallIssue]


# =============================================================================
# Unified mode (LCORE-836)
# =============================================================================


def test_llama_stack_unified_mode_library_client() -> None:
    """Unified mode in library mode: `config` set, no library_client_config_path."""
    # pylint: disable=import-outside-toplevel
    from models.config import UnifiedLlamaStackConfig

    cfg = LlamaStackConfiguration(
        use_as_library_client=True,
        config=UnifiedLlamaStackConfig(),
    )  # pyright: ignore[reportCallIssue]
    assert cfg.config is not None
    assert cfg.library_client_config_path is None


def test_llama_stack_unified_and_legacy_are_mutually_exclusive() -> None:
    """Setting both `config` and `library_client_config_path` is rejected."""
    # pylint: disable=import-outside-toplevel
    from models.config import UnifiedLlamaStackConfig

    with pytest.raises(
        ValueError,
        match="mutually exclusive",
    ):
        LlamaStackConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
            config=UnifiedLlamaStackConfig(),
        )  # pyright: ignore[reportCallIssue]


def test_llama_stack_unified_mode_with_remote_url() -> None:
    """Unified config is also allowed when connecting to a remote Llama Stack."""
    # pylint: disable=import-outside-toplevel
    from models.config import UnifiedLlamaStackConfig

    cfg = LlamaStackConfiguration(
        url="http://remote-ls:8321",
        config=UnifiedLlamaStackConfig(),
    )  # pyright: ignore[reportCallIssue]
    assert cfg.config is not None
    assert str(cfg.url) == "http://remote-ls:8321/"


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

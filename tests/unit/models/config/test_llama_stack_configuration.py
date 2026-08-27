"""Unit tests for OgxConfiguration model."""

import copy
from typing import Any

import pytest
import yaml
from pydantic import AnyHttpUrl, ValidationError
from pytest_subtests import SubTests

import constants
from models.config import (
    Configuration,
    OgxConfiguration,
    UnifiedOgxConfig,
)
from utils.checks import InvalidConfigurationError

# A complete, valid lightspeed-stack.yaml used as the base for root-model
# (Configuration) validation tests; individual tests override its llama_stack
# and inference sections to exercise unified-vs-legacy mode detection.
_BASE_CONFIG_PATH = "tests/configuration/lightspeed-stack.yaml"


def _base_config_dict() -> dict[str, Any]:
    """Load the base lightspeed-stack.yaml fixture as a fresh dict."""
    with open(_BASE_CONFIG_PATH, "r", encoding="utf-8") as file:
        return copy.deepcopy(yaml.safe_load(file))


def test_llama_stack_configuration_constructor(subtests: SubTests) -> None:
    """
    Verify that the OgxConfiguration constructor accepts
    valid combinations of parameters and creates instances
    successfully.
    """
    with subtests.test(msg="Configuration for library mode"):
        llama_stack_configuration = OgxConfiguration(
            use_as_library_client=True,
            library_client_config_path="tests/configuration/run.yaml",
            url=None,
            api_key=None,
            timeout=60,
        )
        assert llama_stack_configuration is not None
        assert llama_stack_configuration.allow_degraded_mode is False
        assert llama_stack_configuration.max_retries == constants.DEFAULT_MAX_RETRIES
        assert llama_stack_configuration.retry_delay == constants.DEFAULT_RETRY_DELAY

    with subtests.test(msg="Configuration for server mode"):
        llama_stack_configuration = OgxConfiguration(
            use_as_library_client=False,
            url=AnyHttpUrl("http://localhost"),
            library_client_config_path=None,
            api_key=None,
            timeout=60,
        )
        assert llama_stack_configuration is not None
        assert llama_stack_configuration.allow_degraded_mode is False
        assert llama_stack_configuration.max_retries == constants.DEFAULT_MAX_RETRIES
        assert llama_stack_configuration.retry_delay == constants.DEFAULT_RETRY_DELAY

    with subtests.test(msg="Minimal configuration for server mode"):
        llama_stack_configuration = OgxConfiguration(
            url="http://localhost"
        )  # pyright: ignore[reportCallIssue]
        assert llama_stack_configuration is not None
        assert llama_stack_configuration.allow_degraded_mode is False
        assert llama_stack_configuration.max_retries == constants.DEFAULT_MAX_RETRIES
        assert llama_stack_configuration.retry_delay == constants.DEFAULT_RETRY_DELAY

    with subtests.test(msg="Full configuration for server mode"):
        llama_stack_configuration = OgxConfiguration(
            use_as_library_client=False, url="http://localhost", api_key="foo"
        )  # pyright: ignore[reportCallIssue]
        assert llama_stack_configuration is not None
        assert llama_stack_configuration.allow_degraded_mode is False
        assert llama_stack_configuration.max_retries == constants.DEFAULT_MAX_RETRIES
        assert llama_stack_configuration.retry_delay == constants.DEFAULT_RETRY_DELAY

    with subtests.test(msg="Degraded mode enabled"):
        llama_stack_configuration = OgxConfiguration(
            url="http://localhost",
            allow_degraded_mode=True,
        )  # pyright: ignore[reportCallIssue]
        assert llama_stack_configuration is not None
        assert llama_stack_configuration.allow_degraded_mode is True
        assert llama_stack_configuration.max_retries == constants.DEFAULT_MAX_RETRIES
        assert llama_stack_configuration.retry_delay == constants.DEFAULT_RETRY_DELAY


def test_llama_stack_configuration_no_run_yaml() -> None:
    """
    Verify that constructing a OgxConfiguration with a
    non-existent or invalid library_client_config_path raises
    InvalidConfigurationError.
    """
    with pytest.raises(
        InvalidConfigurationError,
        match="OGX configuration file 'not a file' is not a file",
    ):
        OgxConfiguration(
            use_as_library_client=True,
            library_client_config_path="not a file",
        )  # pyright: ignore[reportCallIssue]


def test_llama_stack_wrong_configuration_constructor_no_url() -> None:
    """
    Verify that constructing a OgxConfiguration without
    specifying either a URL or enabling library client mode raises
    a ValueError.
    """
    with pytest.raises(
        ValueError,
        match="OGX URL is not specified and library client mode is not specified",
    ):
        OgxConfiguration()  # pyright: ignore[reportCallIssue]


def test_llama_stack_wrong_configuration_constructor_library_mode_off() -> None:
    """Test the OgxConfiguration constructor."""
    with pytest.raises(
        ValueError,
        match="OGX URL is not specified and library client mode is not enabled",
    ):
        OgxConfiguration(
            use_as_library_client=False
        )  # pyright: ignore[reportCallIssue]


def test_llama_stack_library_mode_without_source_is_allowed_on_nested_model() -> None:
    """The nested model no longer requires a run source in library mode.

    A library-mode config may be driven by the root-level inference.providers,
    which this nested model cannot see, so the "needs a run source" check moved
    to the root Configuration model (see
    test_root_rejects_library_mode_without_run_source). Constructing the nested
    model alone with neither a path nor a config block must therefore succeed.
    """
    cfg = OgxConfiguration(
        use_as_library_client=True
    )  # pyright: ignore[reportCallIssue]
    assert cfg.use_as_library_client is True
    assert cfg.library_client_config_path is None
    assert cfg.config is None


def test_llama_stack_configuration_valid_http_url() -> None:
    """Test that valid HTTP URLs are accepted."""
    config = OgxConfiguration(
        url="http://localhost:8321"
    )  # pyright: ignore[reportCallIssue]
    assert config is not None
    assert str(config.url) == "http://localhost:8321/"


def test_llama_stack_configuration_valid_https_url() -> None:
    """Test that valid HTTPS URLs are accepted."""
    config = OgxConfiguration(
        url="https://llama-stack.example.com:8321"
    )  # pyright: ignore[reportCallIssue]
    assert config is not None
    assert str(config.url) == "https://llama-stack.example.com:8321/"


def test_llama_stack_configuration_malformed_url_rejected() -> None:
    """Test that malformed URLs are rejected with a ValidationError."""
    with pytest.raises(ValidationError, match="Input should be a valid URL"):
        OgxConfiguration(url="not-a-valid-url")  # pyright: ignore[reportCallIssue]


def test_llama_stack_configuration_invalid_scheme_rejected() -> None:
    """Test that URLs without http/https scheme are rejected."""
    with pytest.raises(ValidationError, match="URL scheme should be 'http' or 'https'"):
        OgxConfiguration(url="ftp://localhost:8321")  # pyright: ignore[reportCallIssue]


def test_llama_stack_configuration_wrong_max_retries_count(subtests: SubTests) -> None:
    """Test that malformed URLs are rejected with a ValidationError."""
    with subtests.test(msg="Configuration with zero max_retries count"):
        with pytest.raises(ValidationError, match="Input should be greater than 0"):
            OgxConfiguration(
                url="https://llama-stack.example.com:8321",
                max_retries=0,
            )  # pyright: ignore[reportCallIssue]
    with subtests.test(msg="Configuration with negative max_retries count"):
        with pytest.raises(ValidationError, match="Input should be greater than 0"):
            OgxConfiguration(
                url="https://llama-stack.example.com:8321",
                max_retries=-1,
            )  # pyright: ignore[reportCallIssue]


def test_llama_stack_configuration_wrong_retry_delay_value(subtests: SubTests) -> None:
    """Test that malformed URLs are rejected with a ValidationError."""
    with subtests.test(msg="Configuration with zero retry_delay value"):
        with pytest.raises(ValidationError, match="Input should be greater than 0"):
            OgxConfiguration(
                url="https://llama-stack.example.com:8321",
                retry_delay=0,
            )  # pyright: ignore[reportCallIssue]
    with subtests.test(msg="Configuration with negative retry_delay value"):
        with pytest.raises(ValidationError, match="Input should be greater than 0"):
            OgxConfiguration(
                url="https://llama-stack.example.com:8321",
                retry_delay=-1,
            )  # pyright: ignore[reportCallIssue]


# ---------------------------------------------------------------------------
# Unified-mode schema (LCORE-2336)
# ---------------------------------------------------------------------------


def test_library_mode_with_unified_config_no_path_is_valid() -> None:
    """Library mode driven by llama_stack.config needs no library_client_config_path."""
    cfg = OgxConfiguration(
        use_as_library_client=True,
        config=UnifiedOgxConfig(),
    )  # pyright: ignore[reportCallIssue]
    assert cfg.config is not None
    assert cfg.library_client_config_path is None


def test_unified_config_rejects_unknown_fields() -> None:
    """UnifiedOgxConfig forbids extra keys (extra='forbid', R9)."""
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        UnifiedOgxConfig(bogus=True)  # pyright: ignore[reportCallIssue]


def test_unified_config_accepts_byo_llm_baseline() -> None:
    """byo-llm is a valid baseline selector (LCORE-3654)."""
    cfg = UnifiedOgxConfig(baseline="byo-llm")
    assert cfg.baseline == "byo-llm"


def test_root_rejects_config_and_legacy_path_together() -> None:
    """A llama_stack.config block and a legacy path in one file fail at load (R3)."""
    config_dict = _base_config_dict()
    config_dict["llama_stack"] = {
        "use_as_library_client": True,
        "library_client_config_path": "tests/configuration/run.yaml",
        "config": {"baseline": "default"},
    }
    with pytest.raises(ValidationError, match="--migrate-config"):
        Configuration(**config_dict)


def test_root_rejects_inference_providers_and_legacy_path_together() -> None:
    """Top-level inference.providers plus a legacy path fail at load (R3)."""
    config_dict = _base_config_dict()
    config_dict["llama_stack"] = {
        "use_as_library_client": True,
        "library_client_config_path": "tests/configuration/run.yaml",
    }
    config_dict["inference"] = {
        "providers": [{"type": "openai", "api_key_env": "OPENAI_API_KEY"}]
    }
    with pytest.raises(ValidationError, match="mutually exclusive"):
        Configuration(**config_dict)


def test_root_rejects_vector_store_providers_and_legacy_path_together() -> None:
    """Non-empty vector_store.providers plus a legacy path fail at load."""
    config_dict = _base_config_dict()
    config_dict["llama_stack"] = {
        "use_as_library_client": True,
        "library_client_config_path": "tests/configuration/run.yaml",
    }
    config_dict["vector_store"] = {
        "default_provider": "notebooks",
        "providers": [
            {
                "id": "notebooks",
                "type": "faiss",
                "embedding_model": "/rag-content/embeddings_model",
                "embedding_dimension": 768,
                "config": {"path": "/var/lib/notebooks.db"},
            }
        ],
    }
    with pytest.raises(ValidationError, match="mutually exclusive"):
        Configuration(**config_dict)


def test_root_accepts_vector_store_providers_only_no_config_block() -> None:
    """Library mode driven by vector_store.providers alone is valid."""
    config_dict = _base_config_dict()
    config_dict["llama_stack"] = {"use_as_library_client": True}
    config_dict["inference"] = {"providers": []}
    config_dict["vector_store"] = {
        "default_provider": "notebooks",
        "providers": [
            {
                "id": "notebooks",
                "type": "faiss",
                "embedding_model": "/rag-content/embeddings_model",
                "embedding_dimension": 768,
                "config": {"path": "/var/lib/notebooks.db"},
            }
        ],
    }
    cfg = Configuration(**config_dict)
    # pylint: disable=no-member
    assert cfg.llama_stack.config is None
    assert cfg.vector_store.default_provider == "notebooks"
    assert len(cfg.vector_store.providers) == 1


def test_root_accepts_unified_library_config() -> None:
    """A unified library-mode config (no legacy path) loads cleanly (R1)."""
    config_dict = _base_config_dict()
    config_dict["llama_stack"] = {
        "use_as_library_client": True,
        "config": {"baseline": "default"},
    }
    config_dict["inference"] = {
        "providers": [{"type": "openai", "api_key_env": "OPENAI_API_KEY"}]
    }
    cfg = Configuration(**config_dict)
    # pylint: disable=no-member
    assert cfg.llama_stack.config is not None
    assert cfg.inference.providers[0].type == "openai"


def test_root_accepts_inference_providers_only_no_config_block() -> None:
    """Library mode driven by inference.providers alone is valid (UX: no config:{}).

    The minimal unified library config needs no llama_stack.config block — a
    non-empty top-level inference.providers is a sufficient synthesis input.
    """
    config_dict = _base_config_dict()
    config_dict["llama_stack"] = {"use_as_library_client": True}
    config_dict["inference"] = {
        "providers": [{"type": "openai", "api_key_env": "OPENAI_API_KEY"}]
    }
    cfg = Configuration(**config_dict)
    # pylint: disable=no-member
    assert cfg.llama_stack.config is None
    assert cfg.inference.providers[0].type == "openai"


def test_root_rejects_library_mode_without_run_source() -> None:
    """Library mode with no synthesis input and no legacy path fails at load."""
    config_dict = _base_config_dict()
    config_dict["llama_stack"] = {"use_as_library_client": True}
    config_dict["inference"] = {"providers": []}
    with pytest.raises(ValidationError, match="requires a run-configuration source"):
        Configuration(**config_dict)


def test_root_accepts_remote_url_with_unified_config() -> None:
    """url + unified config (server mode) is allowed — url is orthogonal (R11)."""
    config_dict = _base_config_dict()
    config_dict["llama_stack"] = {
        "use_as_library_client": False,
        "url": "http://localhost:8321",
        "config": {"baseline": "default"},
    }
    cfg = Configuration(**config_dict)
    assert cfg.llama_stack.config is not None  # pylint: disable=no-member


# ---------------------------------------------------------------------------
# config_format_version cross-validation (LCORE-2872, R11)
# ---------------------------------------------------------------------------


def _unified_body(config_dict: dict[str, Any]) -> dict[str, Any]:
    """Give the base config a unified shape (synthesis input present)."""
    config_dict["llama_stack"] = {"use_as_library_client": True}
    config_dict["inference"] = {
        "providers": [{"type": "openai", "api_key_env": "OPENAI_API_KEY"}]
    }
    return config_dict


def _clear_synthesis_inputs(config_dict: dict[str, Any]) -> dict[str, Any]:
    """Explicitly empty both provider lists the unified detection looks at.

    The base fixture carries neither section today, but the legacy/remote
    helpers must not silently become unified-shaped if it ever gains one.
    """
    config_dict["inference"] = {"providers": []}
    config_dict["vector_store"] = {"providers": []}
    return config_dict


def _legacy_body(config_dict: dict[str, Any]) -> dict[str, Any]:
    """Give the base config a legacy shape (external run.yaml path)."""
    config_dict = _clear_synthesis_inputs(config_dict)
    config_dict["llama_stack"] = {
        "use_as_library_client": True,
        "library_client_config_path": "tests/configuration/run.yaml",
    }
    return config_dict


def _remote_body(config_dict: dict[str, Any]) -> dict[str, Any]:
    """Give the base config a remote shape (url only, no synthesis input)."""
    config_dict = _clear_synthesis_inputs(config_dict)
    config_dict["llama_stack"] = {
        "use_as_library_client": False,
        "url": "http://localhost:8321",
    }
    return config_dict


def test_root_config_format_version_defaults_to_none() -> None:
    """The field is optional; an unversioned config loads with None."""
    cfg = Configuration(**_unified_body(_base_config_dict()))
    assert cfg.config_format_version is None


def test_root_accepts_config_format_version_unified_with_unified_body() -> None:
    """'unified' agrees with a body that has a synthesis input."""
    config_dict = _unified_body(_base_config_dict())
    config_dict["config_format_version"] = "unified"
    cfg = Configuration(**config_dict)
    assert cfg.config_format_version == "unified"


def test_root_accepts_config_format_version_legacy_with_legacy_body() -> None:
    """'legacy' agrees with a body driven by library_client_config_path."""
    config_dict = _legacy_body(_base_config_dict())
    config_dict["config_format_version"] = "legacy"
    cfg = Configuration(**config_dict)
    assert cfg.config_format_version == "legacy"


def test_root_accepts_config_format_version_legacy_with_remote_body() -> None:
    """'legacy' agrees with a remote-only body (no synthesis input)."""
    config_dict = _remote_body(_base_config_dict())
    config_dict["config_format_version"] = "legacy"
    cfg = Configuration(**config_dict)
    assert cfg.config_format_version == "legacy"


def test_root_rejects_config_format_version_legacy_with_unified_body() -> None:
    """'legacy' with a unified-shaped body fails; error names the field."""
    config_dict = _unified_body(_base_config_dict())
    config_dict["config_format_version"] = "legacy"
    with pytest.raises(ValidationError, match="config_format_version"):
        Configuration(**config_dict)


def test_root_rejects_config_format_version_unified_with_legacy_body() -> None:
    """'unified' with a legacy-shaped body fails; error names the field."""
    config_dict = _legacy_body(_base_config_dict())
    config_dict["config_format_version"] = "unified"
    with pytest.raises(ValidationError, match="config_format_version"):
        Configuration(**config_dict)


def test_root_rejects_config_format_version_unified_with_remote_body() -> None:
    """'unified' with a remote-only body (no synthesis input) fails."""
    config_dict = _remote_body(_base_config_dict())
    config_dict["config_format_version"] = "unified"
    with pytest.raises(ValidationError, match="config_format_version"):
        Configuration(**config_dict)


def test_root_rejects_unknown_config_format_version_value() -> None:
    """Values outside the 'legacy'/'unified' literal are rejected."""
    config_dict = _unified_body(_base_config_dict())
    config_dict["config_format_version"] = "v2"
    with pytest.raises(ValidationError, match="Input should be 'legacy' or 'unified'"):
        Configuration(**config_dict)


def test_root_accepts_unified_marker_with_vector_store_providers_body() -> None:
    """'unified' agrees with a body whose only synthesis input is vector_store."""
    config_dict = _base_config_dict()
    config_dict["llama_stack"] = {"use_as_library_client": True}
    config_dict["inference"] = {"providers": []}
    config_dict["vector_store"] = {
        "default_provider": "notebooks",
        "providers": [
            {
                "id": "notebooks",
                "type": "faiss",
                "embedding_model": "/rag-content/embeddings_model",
                "embedding_dimension": 768,
                "config": {"path": "/var/lib/notebooks.db"},
            }
        ],
    }
    config_dict["config_format_version"] = "unified"
    cfg = Configuration(**config_dict)
    assert cfg.config_format_version == "unified"


def test_root_accepts_unified_marker_with_config_block_body() -> None:
    """'unified' agrees with a body whose only synthesis input is llama_stack.config."""
    config_dict = _clear_synthesis_inputs(_base_config_dict())
    config_dict["llama_stack"] = {
        "use_as_library_client": True,
        "config": {"baseline": "default"},
    }
    config_dict["config_format_version"] = "unified"
    cfg = Configuration(**config_dict)
    assert cfg.config_format_version == "unified"


def test_missing_run_source_error_precedes_marker_check() -> None:
    """Library mode without a run source fails on that, not on the marker.

    A 'unified' marker on a sourceless library config is also a mismatch,
    but the missing-run-source check runs first and its error must win.
    """
    config_dict = _clear_synthesis_inputs(_base_config_dict())
    config_dict["llama_stack"] = {"use_as_library_client": True}
    config_dict["config_format_version"] = "unified"
    with pytest.raises(ValidationError, match="requires a run-configuration source"):
        Configuration(**config_dict)


def test_mutual_exclusion_error_precedes_marker_check() -> None:
    """Ambiguous unified+legacy bodies fail on mutual exclusion, not the marker.

    A 'legacy' marker on such a body is also a mismatch (the body carries a
    synthesis input), but the mutual-exclusion check runs first and its
    --migrate-config guidance must win.
    """
    config_dict = _unified_body(_base_config_dict())
    config_dict["llama_stack"][
        "library_client_config_path"
    ] = "tests/configuration/run.yaml"
    config_dict["config_format_version"] = "legacy"
    with pytest.raises(ValidationError, match="mutually exclusive"):
        Configuration(**config_dict)

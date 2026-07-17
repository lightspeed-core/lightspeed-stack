"""Unit tests for ObservabilityConfiguration model."""

import os

import pytest

from lightspeed_stack.models.config import ObservabilityConfiguration


def test_default_values() -> None:
    """Test default ObservabilityConfiguration has expected values."""
    cfg = ObservabilityConfiguration()
    assert cfg.otel == {}


def test_from_environment_no_otel_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test from_environment with no OTEL_* environment variables.

    Parameters:
    ----------
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for environment manipulation.
    """
    # Clear any existing OTEL_ variables
    for key in list(os.environ.keys()):
        if key.startswith("OTEL_"):
            monkeypatch.delenv(key, raising=False)

    cfg = ObservabilityConfiguration.from_environment()
    assert cfg.otel == {}


def test_from_environment_with_otel_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test from_environment collects OTEL_* environment variables.

    Parameters:
    ----------
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for environment manipulation.
    """
    # Set OTEL_ environment variables
    otel_vars = {
        "OTEL_SDK_DISABLED": "true",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
        "OTEL_SERVICE_NAME": "lightspeed-stack",
    }

    for key, value in otel_vars.items():
        monkeypatch.setenv(key, value)

    cfg = ObservabilityConfiguration.from_environment()

    # Verify all OTEL_ vars are collected
    for key, value in otel_vars.items():
        assert key in cfg.otel
        assert cfg.otel[key] == value


def test_from_environment_ignores_non_otel_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test from_environment only collects OTEL_* variables.

    Parameters:
    ----------
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for environment manipulation.
    """
    # Set some non-OTEL variables
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/home/user")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")

    cfg = ObservabilityConfiguration.from_environment()

    # Only OTEL_ vars should be collected
    assert "PATH" not in cfg.otel
    assert "HOME" not in cfg.otel
    assert "OTEL_SDK_DISABLED" in cfg.otel
    assert cfg.otel["OTEL_SDK_DISABLED"] == "true"


def test_manual_construction() -> None:
    """Test manual construction of ObservabilityConfiguration."""
    otel_dict = {
        "OTEL_SDK_DISABLED": "false",
        "OTEL_SERVICE_NAME": "test-service",
    }

    cfg = ObservabilityConfiguration(otel=otel_dict)

    assert cfg.otel == otel_dict
    assert cfg.otel["OTEL_SDK_DISABLED"] == "false"
    assert cfg.otel["OTEL_SERVICE_NAME"] == "test-service"


@pytest.mark.parametrize(
    ("otel_dict", "expected_count"),
    [
        ({}, 0),
        ({"OTEL_SDK_DISABLED": "true"}, 1),
        (
            {
                "OTEL_SDK_DISABLED": "true",
                "OTEL_SERVICE_NAME": "test",
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
            },
            3,
        ),
    ],
    ids=[
        "empty",
        "single_var",
        "multiple_vars",
    ],
)
def test_otel_dict_sizes(otel_dict: dict[str, str], expected_count: int) -> None:
    """Test ObservabilityConfiguration with various otel dict sizes.

    Parameters:
    ----------
        otel_dict (dict[str, str]): Dictionary of OTEL environment variables to test.
        expected_count (int): Expected number of items in the resulting otel dict.
    """
    cfg = ObservabilityConfiguration(otel=otel_dict)
    assert len(cfg.otel) == expected_count


def test_otel_empty_string_values() -> None:
    """Test ObservabilityConfiguration handles empty string values."""
    otel_dict = {
        "OTEL_EXPORTER_OTLP_ENDPOINT": "",
        "OTEL_SERVICE_NAME": "",
    }

    cfg = ObservabilityConfiguration(otel=otel_dict)

    assert cfg.otel["OTEL_EXPORTER_OTLP_ENDPOINT"] == ""
    assert cfg.otel["OTEL_SERVICE_NAME"] == ""


def test_model_config_extra_forbid() -> None:
    """Test that extra fields are forbidden (inherited from ConfigurationBase)."""
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        ObservabilityConfiguration(
            otel={},
            unexpected_field="value",  # type: ignore[call-arg]
        )


def test_from_environment_redacts_secret_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that OTEL_EXPORTER_OTLP_HEADERS values are redacted.

    Parameters:
    ----------
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for environment manipulation.
    """
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_HEADERS", "api-key=secret_token,tenant-id=acme"
    )
    monkeypatch.setenv("OTEL_SERVICE_NAME", "test-service")

    cfg = ObservabilityConfiguration.from_environment()

    # Header values should be redacted but keys preserved
    assert "OTEL_EXPORTER_OTLP_HEADERS" in cfg.otel
    assert (
        cfg.otel["OTEL_EXPORTER_OTLP_HEADERS"]
        == "api-key=[REDACTED],tenant-id=[REDACTED]"
    )

    # Non-secret vars should not be redacted
    assert "OTEL_SERVICE_NAME" in cfg.otel
    assert cfg.otel["OTEL_SERVICE_NAME"] == "test-service"


def test_from_environment_redacts_mtls_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that mTLS certificate and key paths are redacted.

    Parameters:
    ----------
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for environment manipulation.
    """
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_CERTIFICATE", "/path/to/cert.pem")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_CLIENT_KEY", "/path/to/key.pem")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "false")

    cfg = ObservabilityConfiguration.from_environment()

    # All mTLS-related vars should be redacted
    assert cfg.otel["OTEL_EXPORTER_OTLP_CERTIFICATE"] == "[REDACTED]"
    assert cfg.otel["OTEL_EXPORTER_OTLP_CLIENT_KEY"] == "[REDACTED]"

    # Non-secret var should not be redacted
    assert cfg.otel["OTEL_SDK_DISABLED"] == "false"


def test_from_environment_redacts_all_secret_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that generic and signal-specific secret OTEL variables are redacted.

    Parameters:
    ----------
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for environment manipulation.
    """
    # Set headers with key=value format
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "api-key=secret")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_HEADERS", "trace-key=secret")

    # Set certificates and keys
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_CERTIFICATE", "/secret/cert.pem")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_CLIENT_KEY", "/secret/key.pem")

    # Also set some non-secret vars
    monkeypatch.setenv("OTEL_SERVICE_NAME", "test-service")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    cfg = ObservabilityConfiguration.from_environment()

    # Headers should have values redacted but keys preserved
    assert cfg.otel["OTEL_EXPORTER_OTLP_HEADERS"] == "api-key=[REDACTED]"
    assert cfg.otel["OTEL_EXPORTER_OTLP_TRACES_HEADERS"] == "trace-key=[REDACTED]"

    # Certificates and keys should be fully redacted
    assert cfg.otel["OTEL_EXPORTER_OTLP_CERTIFICATE"] == "[REDACTED]"
    assert cfg.otel["OTEL_EXPORTER_OTLP_CLIENT_KEY"] == "[REDACTED]"

    # Non-secret vars should not be redacted
    assert cfg.otel["OTEL_SERVICE_NAME"] == "test-service"
    assert cfg.otel["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://localhost:4317"


def test_direct_construction_redacts_secrets() -> None:
    """Test that direct construction also redacts secrets via validator."""
    otel_dict = {
        "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Bearer secret,x-api-key=12345",
        "OTEL_EXPORTER_OTLP_CERTIFICATE": "/path/to/cert.pem",
        "OTEL_EXPORTER_OTLP_CLIENT_KEY": "/path/to/key.pem",
        "OTEL_SERVICE_NAME": "my-service",
        "OTEL_SDK_DISABLED": "false",
    }

    cfg = ObservabilityConfiguration(otel=otel_dict)

    # Header values should be redacted but keys preserved
    assert (
        cfg.otel["OTEL_EXPORTER_OTLP_HEADERS"]
        == "Authorization=[REDACTED],x-api-key=[REDACTED]"
    )

    # Certificates and keys should be fully redacted
    assert cfg.otel["OTEL_EXPORTER_OTLP_CERTIFICATE"] == "[REDACTED]"
    assert cfg.otel["OTEL_EXPORTER_OTLP_CLIENT_KEY"] == "[REDACTED]"

    # Non-secrets should not be redacted
    assert cfg.otel["OTEL_SERVICE_NAME"] == "my-service"
    assert cfg.otel["OTEL_SDK_DISABLED"] == "false"


def test_signal_specific_headers_redacted() -> None:
    """Test that signal-specific OTLP headers have values redacted."""
    otel_dict = {
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS": "Authorization=Bearer trace-token",
        "OTEL_EXPORTER_OTLP_METRICS_HEADERS": "x-api-key=metrics-key,tenant=prod",
        "OTEL_EXPORTER_OTLP_LOGS_HEADERS": "api-key=logs-token",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4317",
    }

    cfg = ObservabilityConfiguration(otel=otel_dict)

    # All signal-specific header values should be redacted but keys preserved
    assert cfg.otel["OTEL_EXPORTER_OTLP_TRACES_HEADERS"] == "Authorization=[REDACTED]"
    assert (
        cfg.otel["OTEL_EXPORTER_OTLP_METRICS_HEADERS"]
        == "x-api-key=[REDACTED],tenant=[REDACTED]"
    )
    assert cfg.otel["OTEL_EXPORTER_OTLP_LOGS_HEADERS"] == "api-key=[REDACTED]"

    # Non-secret should not be redacted
    assert cfg.otel["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://collector:4317"


def test_signal_specific_certificates_redacted() -> None:
    """Test that signal-specific OTLP certificates and keys are redacted."""
    otel_dict = {
        "OTEL_EXPORTER_OTLP_TRACES_CERTIFICATE": "/path/to/traces-cert.pem",
        "OTEL_EXPORTER_OTLP_METRICS_CERTIFICATE": "/path/to/metrics-cert.pem",
        "OTEL_EXPORTER_OTLP_TRACES_CLIENT_KEY": "/path/to/traces-key.pem",
        "OTEL_EXPORTER_OTLP_METRICS_CLIENT_KEY": "/path/to/metrics-key.pem",
        "OTEL_SERVICE_NAME": "test-service",
    }

    cfg = ObservabilityConfiguration(otel=otel_dict)

    # All signal-specific certificates and keys should be redacted
    assert cfg.otel["OTEL_EXPORTER_OTLP_TRACES_CERTIFICATE"] == "[REDACTED]"
    assert cfg.otel["OTEL_EXPORTER_OTLP_METRICS_CERTIFICATE"] == "[REDACTED]"
    assert cfg.otel["OTEL_EXPORTER_OTLP_TRACES_CLIENT_KEY"] == "[REDACTED]"
    assert cfg.otel["OTEL_EXPORTER_OTLP_METRICS_CLIENT_KEY"] == "[REDACTED]"

    # Non-secret should not be redacted
    assert cfg.otel["OTEL_SERVICE_NAME"] == "test-service"


def test_validator_does_not_mutate_input() -> None:
    """Test that the validator returns a new dict without mutating input."""
    original_dict = {
        "OTEL_EXPORTER_OTLP_HEADERS": "api-key=secret-token",
        "OTEL_SERVICE_NAME": "test-service",
    }

    # Create a copy to verify original isn't mutated
    original_copy = original_dict.copy()

    cfg = ObservabilityConfiguration(otel=original_dict)

    # Original dict should be unchanged
    assert original_dict == original_copy
    assert original_dict["OTEL_EXPORTER_OTLP_HEADERS"] == "api-key=secret-token"

    # But the config should have redacted value
    assert cfg.otel["OTEL_EXPORTER_OTLP_HEADERS"] == "api-key=[REDACTED]"


def test_header_redaction_edge_cases() -> None:
    """Test header value redaction handles various formats correctly."""
    # Multiple key=value pairs
    otel_dict = {
        "OTEL_EXPORTER_OTLP_HEADERS": "api-key=secret1,tenant-id=acme,x-trace-id=12345",
    }
    cfg = ObservabilityConfiguration(otel=otel_dict)
    assert (
        cfg.otel["OTEL_EXPORTER_OTLP_HEADERS"]
        == "api-key=[REDACTED],tenant-id=[REDACTED],x-trace-id=[REDACTED]"
    )

    # Single key=value pair
    otel_dict2 = {"OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Bearer token123"}
    cfg2 = ObservabilityConfiguration(otel=otel_dict2)
    assert cfg2.otel["OTEL_EXPORTER_OTLP_HEADERS"] == "Authorization=[REDACTED]"

    # No equals sign (malformed, redact entirely)
    otel_dict3 = {"OTEL_EXPORTER_OTLP_HEADERS": "just-a-token"}
    cfg3 = ObservabilityConfiguration(otel=otel_dict3)
    assert cfg3.otel["OTEL_EXPORTER_OTLP_HEADERS"] == "[REDACTED]"

    # Empty string
    otel_dict4 = {"OTEL_EXPORTER_OTLP_HEADERS": ""}
    cfg4 = ObservabilityConfiguration(otel=otel_dict4)
    assert cfg4.otel["OTEL_EXPORTER_OTLP_HEADERS"] == "[REDACTED]"


def test_validator_handles_invalid_input_types() -> None:
    """Test that validator allows Pydantic to handle non-dict inputs."""
    # Non-dict inputs should raise Pydantic validation errors, not AttributeError
    with pytest.raises(ValueError, match="Input should be a valid dictionary"):
        ObservabilityConfiguration(otel="not-a-dict")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Input should be a valid dictionary"):
        ObservabilityConfiguration(otel=123)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Input should be a valid dictionary"):
        ObservabilityConfiguration(otel=["list", "of", "values"])  # type: ignore[arg-type]

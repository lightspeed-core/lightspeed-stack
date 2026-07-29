"""Unit tests for ObservabilityConfiguration model."""

import os

import pytest

from models.config import ObservabilityConfiguration


def test_default_values() -> None:
    """Test default ObservabilityConfiguration has expected values."""
    cfg = ObservabilityConfiguration()
    assert cfg.otel == {}


def test_from_environment_no_otel_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test from_environment with no OTEL_* environment variables."""
    # Clear any existing OTEL_ variables
    for key in list(os.environ.keys()):
        if key.startswith("OTEL_"):
            monkeypatch.delenv(key, raising=False)

    cfg = ObservabilityConfiguration.from_environment()
    assert cfg.otel == {}


def test_from_environment_with_otel_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test from_environment collects OTEL_* environment variables."""
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
    """Test from_environment only collects OTEL_* variables."""
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
    """Test ObservabilityConfiguration with various otel dict sizes."""
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

"""Unit tests for ServiceConfiguration model."""

import pytest

from pydantic import ValidationError

from models.config import ServiceConfiguration, TLSConfiguration


def test_service_configuration_constructor() -> None:
    """
    Verify that the ServiceConfiguration constructor sets default
    values for all fields.
    """
    s = ServiceConfiguration()  # pyright: ignore[reportCallIssue]
    assert s is not None

    assert s.host == "localhost"
    assert s.port == 8080
    assert s.auth_enabled is False
    assert s.workers == 1
    assert s.root_path == ""
    assert s.color_log is True
    assert s.access_log is True
    assert s.tls_config == TLSConfiguration()  # pyright: ignore[reportCallIssue]


def test_service_configuration_port_value() -> None:
    """Test the ServiceConfiguration port value validation."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        ServiceConfiguration(port=-1)  # pyright: ignore[reportCallIssue]

    with pytest.raises(ValueError, match="Port value should be less than 65536"):
        ServiceConfiguration(port=100000)  # pyright: ignore[reportCallIssue]


def test_service_configuration_root_path() -> None:
    """Test the ServiceConfiguration root_path field."""
    s = ServiceConfiguration(
        root_path="/api/lightspeed"
    )  # pyright: ignore[reportCallIssue]
    assert s.root_path == "/api/lightspeed"


def test_service_configuration_root_path_validation() -> None:
    """Test root_path validation rejects invalid formats."""
    with pytest.raises(ValidationError, match="root_path must start with '/'"):
        ServiceConfiguration(
            root_path="api/lightspeed"
        )  # pyright: ignore[reportCallIssue]

    with pytest.raises(ValidationError, match="root_path must not end with '/'"):
        ServiceConfiguration(
            root_path="/api/lightspeed/"
        )  # pyright: ignore[reportCallIssue]


def test_service_configuration_workers_value() -> None:
    """Test the ServiceConfiguration workers value validation."""
    with pytest.raises(ValidationError, match="Input should be greater than 0"):
        ServiceConfiguration(workers=-1)  # pyright: ignore[reportCallIssue]

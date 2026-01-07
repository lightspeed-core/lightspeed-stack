"""Unit tests for TLSConfiguration model."""

from pathlib import Path

import pytest

from models.config import ServiceConfiguration, TLSConfiguration


def test_tls_configuration() -> None:
    """Test the TLS configuration."""
    cfg = TLSConfiguration(
        tls_certificate_path=Path("tests/configuration/server.crt"),
        tls_key_path=Path("tests/configuration/server.key"),
        tls_key_password=Path("tests/configuration/password"),
    )
    assert cfg is not None
    assert cfg.tls_certificate_path == Path("tests/configuration/server.crt")
    assert cfg.tls_key_path == Path("tests/configuration/server.key")
    assert cfg.tls_key_password == Path("tests/configuration/password")


def test_tls_configuration_in_service_configuration() -> None:
    """Test the TLS configuration in service configuration."""
    # pylint: disable=no-member
    cfg = ServiceConfiguration(
        tls_config=TLSConfiguration(
            tls_certificate_path=Path("tests/configuration/server.crt"),
            tls_key_path=Path("tests/configuration/server.key"),
            tls_key_password=Path("tests/configuration/password"),
        )
    )
    assert cfg is not None
    assert cfg.tls_config is not None
    assert cfg.tls_config.tls_certificate_path == Path("tests/configuration/server.crt")
    assert cfg.tls_config.tls_key_path == Path("tests/configuration/server.key")
    assert cfg.tls_config.tls_key_password == Path("tests/configuration/password")


def test_tls_configuration_wrong_certificate_path() -> None:
    """Test the TLS configuration loading when some path is broken."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path=Path("this-is-wrong"),
            tls_key_path=Path("tests/configuration/server.key"),
            tls_key_password=Path("tests/configuration/password"),
        )


def test_tls_configuration_wrong_key_path() -> None:
    """Test the TLS configuration loading when some path is broken."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path=Path("tests/configurationserver.crt"),
            tls_key_path=Path("this-is-wrong"),
            tls_key_password=Path("tests/configuration/password"),
        )


def test_tls_configuration_wrong_password_path() -> None:
    """Test the TLS configuration loading when some path is broken."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path=Path("tests/configurationserver.crt"),
            tls_key_path=Path("tests/configuration/server.key"),
            tls_key_password=Path("this-is-wrong"),
        )


def test_tls_configuration_certificate_path_to_directory() -> None:
    """Test the TLS configuration loading when some path points to a directory.

    Verify that TLSConfiguration raises a ValueError when a provided TLS path
    points to a directory.

    Raises:
        ValueError: If any of the provided TLS paths does not point to a file.
    """
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path=Path("tests/"),
            tls_key_path=Path("tests/configuration/server.key"),
            tls_key_password=Path("tests/configuration/password"),
        )


def test_tls_configuration_key_path_to_directory() -> None:
    """Test the TLS configuration loading when some path points to a directory."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path=Path("tests/configurationserver.crt"),
            tls_key_path=Path("tests/"),
            tls_key_password=Path("tests/configuration/password"),
        )


def test_tls_configuration_password_path_to_directory() -> None:
    """Test the TLS configuration loading when some path points to a directory."""
    with pytest.raises(ValueError, match="Path does not point to a file"):
        TLSConfiguration(
            tls_certificate_path=Path("tests/configurationserver.crt"),
            tls_key_path=Path("tests/configuration/server.key"),
            tls_key_password=Path("tests/"),
        )

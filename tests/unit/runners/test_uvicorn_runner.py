"""Unit tests for the Uvicorn runner implementation."""

import logging
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from constants import LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR
from models.config import ServiceConfiguration, TLSConfiguration
from runners.uvicorn import _resolve_log_level, start_uvicorn


def test_start_uvicorn(mocker: MockerFixture) -> None:
    """Test the function to start Uvicorn server using de-facto default configuration."""
    configuration = ServiceConfiguration(
        host="localhost", port=8080, workers=1
    )  # pyright: ignore[reportCallIssue]

    # don't start real Uvicorn server
    mocked_run = mocker.patch("uvicorn.run")
    start_uvicorn(configuration)
    mocked_run.assert_called_once_with(
        "app.main:app",
        host="localhost",
        port=8080,
        workers=1,
        log_level=20,
        ssl_certfile=None,
        ssl_keyfile=None,
        ssl_keyfile_password="",
        use_colors=True,
        access_log=True,
    )


def test_start_uvicorn_different_host_port(mocker: MockerFixture) -> None:
    """Test the function to start Uvicorn server using custom configuration."""
    configuration = ServiceConfiguration(
        host="x.y.com", port=1234, workers=10
    )  # pyright: ignore[reportCallIssue]

    # don't start real Uvicorn server
    mocked_run = mocker.patch("uvicorn.run")
    start_uvicorn(configuration)
    mocked_run.assert_called_once_with(
        "app.main:app",
        host="x.y.com",
        port=1234,
        workers=10,
        log_level=20,
        ssl_certfile=None,
        ssl_keyfile=None,
        ssl_keyfile_password="",
        use_colors=True,
        access_log=True,
    )


def test_start_uvicorn_empty_tls_configuration(mocker: MockerFixture) -> None:
    """Test the function to start Uvicorn server using empty TLS configuration."""
    tls_config = TLSConfiguration()
    configuration = ServiceConfiguration(
        host="x.y.com", port=1234, workers=10, tls_config=tls_config
    )  # pyright: ignore[reportCallIssue]

    # don't start real Uvicorn server
    mocked_run = mocker.patch("uvicorn.run")
    start_uvicorn(configuration)
    mocked_run.assert_called_once_with(
        "app.main:app",
        host="x.y.com",
        port=1234,
        workers=10,
        log_level=20,
        ssl_certfile=None,
        ssl_keyfile=None,
        ssl_keyfile_password="",
        use_colors=True,
        access_log=True,
    )


def test_start_uvicorn_tls_configuration(mocker: MockerFixture) -> None:
    """Test the function to start Uvicorn server using custom TLS configuration."""
    tls_config = TLSConfiguration(
        tls_certificate_path=Path("tests/configuration/server.crt"),
        tls_key_path=Path("tests/configuration/server.key"),
        tls_key_password=Path("tests/configuration/password"),
    )
    configuration = ServiceConfiguration(
        host="x.y.com", port=1234, workers=10, tls_config=tls_config
    )  # pyright: ignore[reportCallIssue]

    # don't start real Uvicorn server
    mocked_run = mocker.patch("uvicorn.run")
    start_uvicorn(configuration)
    mocked_run.assert_called_once_with(
        "app.main:app",
        host="x.y.com",
        port=1234,
        workers=10,
        log_level=20,
        ssl_certfile=Path("tests/configuration/server.crt"),
        ssl_keyfile=Path("tests/configuration/server.key"),
        ssl_keyfile_password="tests/configuration/password",
        use_colors=True,
        access_log=True,
    )


def test_start_uvicorn_with_root_path(mocker: MockerFixture) -> None:
    """Test that root_path is not passed to uvicorn (it belongs on the FastAPI constructor)."""
    configuration = ServiceConfiguration(
        host="localhost", port=8080, workers=1, root_path="/api/lightspeed"
    )  # pyright: ignore[reportCallIssue]

    # don't start real Uvicorn server
    mocked_run = mocker.patch("uvicorn.run")
    start_uvicorn(configuration)
    mocked_run.assert_called_once_with(
        "app.main:app",
        host="localhost",
        port=8080,
        workers=1,
        log_level=20,
        ssl_certfile=None,
        ssl_keyfile=None,
        ssl_keyfile_password="",
        use_colors=True,
        access_log=True,
    )


@pytest.mark.parametrize(
    ("env_value", "expected_level"),
    [
        ("DEBUG", logging.DEBUG),
        ("debug", logging.DEBUG),
        ("INFO", logging.INFO),
        ("WARNING", logging.WARNING),
        ("ERROR", logging.ERROR),
        ("BOGUS", logging.INFO),
    ],
)
def test_resolve_log_level_from_env(
    monkeypatch: pytest.MonkeyPatch, env_value: str, expected_level: int
) -> None:
    """Test that _resolve_log_level resolves env var values to logging constants."""
    monkeypatch.setenv(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, env_value)
    assert _resolve_log_level() == expected_level


def test_resolve_log_level_defaults_to_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that _resolve_log_level falls back to INFO when the env var is unset."""
    monkeypatch.delenv(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, raising=False)
    assert _resolve_log_level() == logging.INFO


def test_start_uvicorn_respects_debug_log_level(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that start_uvicorn passes the DEBUG log level to uvicorn.run."""
    monkeypatch.setenv(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, "DEBUG")
    configuration = ServiceConfiguration(
        host="localhost", port=8080, workers=1
    )  # pyright: ignore[reportCallIssue]

    mocked_run = mocker.patch("uvicorn.run")
    start_uvicorn(configuration)
    mocked_run.assert_called_once_with(
        "app.main:app",
        host="localhost",
        port=8080,
        workers=1,
        log_level=logging.DEBUG,
        ssl_certfile=None,
        ssl_keyfile=None,
        ssl_keyfile_password="",
        use_colors=True,
        access_log=True,
    )

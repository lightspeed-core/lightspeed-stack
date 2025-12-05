"""Unit tests for the Uvicorn runner implementation."""

from pathlib import Path
from pytest_mock import MockerFixture


from models.config import ServiceConfiguration, TLSConfiguration
from runners.uvicorn import start_uvicorn


def test_start_uvicorn(mocker: MockerFixture) -> None:
    """Test the function to start Uvicorn server using de-facto default configuration."""
    configuration = ServiceConfiguration(host="localhost", port=8080, workers=1)

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
    configuration = ServiceConfiguration(host="x.y.com", port=1234, workers=10)

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
    )

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
    )

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

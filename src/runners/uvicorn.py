"""Uvicorn runner."""

import logging

import uvicorn

from models.config import ServiceConfiguration

logger: logging.Logger = logging.getLogger(__name__)


def _run_uvicorn_server(app_path: str, configuration: ServiceConfiguration, mode: str) -> None:
    """Internal helper to start Uvicorn server."""
    logger.info(f"Starting Uvicorn{' in diagnostic mode' if mode == 'diagnostic' else ''}")

    log_level = logging.INFO

    # please note:
    # TLS fields can be None, which means we will pass those values as None to uvicorn.run
    uvicorn.run(
        app_path,
        host=configuration.host,
        port=configuration.port,
        workers=configuration.workers,
        log_level=log_level,
        ssl_keyfile=configuration.tls_config.tls_key_path,
        ssl_certfile=configuration.tls_config.tls_certificate_path,
        ssl_keyfile_password=str(configuration.tls_config.tls_key_password or ""),
        use_colors=True,
        access_log=True,
    )


def start_uvicorn(configuration: ServiceConfiguration) -> None:
    """Start Uvicorn-based REST API service."""
    _run_uvicorn_server("app.main:app", configuration, "main")


def start_diagnostic_uvicorn(configuration: ServiceConfiguration) -> None:
    """Start Uvicorn-based diagnostic server with minimal app (health endpoints only)."""
    _run_uvicorn_server("app.diagnostic_app:diagnostic_app", configuration, "diagnostic")

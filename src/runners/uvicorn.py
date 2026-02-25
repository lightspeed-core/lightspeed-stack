"""Uvicorn runner."""

import logging

import uvicorn

from log import get_logger, resolve_log_level
from models.config import ServiceConfiguration

logger = get_logger(__name__)


def start_uvicorn(configuration: ServiceConfiguration) -> None:
    """Start the Uvicorn server using the provided service configuration.

    Parameters:
        configuration (ServiceConfiguration): Configuration providing host,
        port, workers, and `tls_config` (including `tls_key_path`,
        `tls_certificate_path`, and `tls_key_password`). TLS fields may be None
        and will be forwarded to uvicorn.run as provided.
    """
    log_level = resolve_log_level()
    logger.info("Starting Uvicorn with log level %s", logging.getLevelName(log_level))

    # please note:
    # TLS fields can be None, which means we will pass those values as None to uvicorn.run
    uvicorn.run(
        "app.main:app",
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

"""Uvicorn runner."""

import logging
import uvicorn

from log import get_logger
from models.config import ServiceConfiguration

logger = get_logger(__name__)


def start_uvicorn(configuration: ServiceConfiguration) -> None:
    """Start Uvicorn-based REST API service."""
    logger.info("Starting Uvicorn")

    log_level = logging.INFO

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

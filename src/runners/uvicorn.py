"""Uvicorn runner."""

import logging
import os

import uvicorn

from constants import DEFAULT_LOG_LEVEL, LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR
from log import get_logger
from models.config import ServiceConfiguration

logger = get_logger(__name__)


def _resolve_log_level() -> int:
    """Resolve the uvicorn log level from the environment.

    Reads the LIGHTSPEED_STACK_LOG_LEVEL environment variable and converts it
    to a Python logging level constant. Falls back to the default log level
    when the variable is unset or contains an invalid value.

    Returns:
        The resolved logging level as an integer constant.
    """
    level_str = os.environ.get(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, DEFAULT_LOG_LEVEL)
    level = getattr(logging, level_str.upper(), None)
    if not isinstance(level, int):
        logger.warning(
            "Invalid log level '%s', falling back to %s",
            level_str,
            DEFAULT_LOG_LEVEL,
        )
        level = getattr(logging, DEFAULT_LOG_LEVEL)
    return level


def start_uvicorn(configuration: ServiceConfiguration) -> None:
    """Start the Uvicorn server using the provided service configuration.

    Parameters:
        configuration (ServiceConfiguration): Configuration providing host,
        port, workers, and `tls_config` (including `tls_key_path`,
        `tls_certificate_path`, and `tls_key_password`). TLS fields may be None
        and will be forwarded to uvicorn.run as provided.
    """
    log_level = _resolve_log_level()
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

"""Log utilities."""

import logging
import logging.config
import os
import sys
import typing as t
from functools import lru_cache
from pathlib import Path

import uvicorn.config
from pydantic.v1.utils import deep_update

from constants import (
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_LEVEL,
    DEFAULT_LOGGER_NAME,
    LIGHTSPEED_STACK_DISABLE_RICH_HANDLER_ENV_VAR,
    LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR,
)


def resolve_log_level() -> int:
    """
    Resolve and validate the log level from environment variable.

    Reads the LIGHTSPEED_STACK_LOG_LEVEL environment variable and validates
    it against Python's logging module. If the environment variable is not set,
    defaults to DEFAULT_LOG_LEVEL. If the value is invalid, logs a warning and
    falls back to DEFAULT_LOG_LEVEL.

    Parameters:
    ----------
        None

    Returns:
    -------
        int: A valid logging level constant (e.g., logging.INFO, logging.DEBUG).
    """
    level_str = os.environ.get(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, DEFAULT_LOG_LEVEL)

    # Validate the level string and convert to logging level constant
    validated_level = getattr(logging, level_str.upper(), None)
    if not isinstance(validated_level, int):
        # Write directly to stderr instead of using a logger. This function is
        # called at module-import time (before logging is configured), so routing
        # through a logger produces inconsistent output depending on root-logger
        # state.
        print(
            f"WARNING: Invalid log level '{level_str}', "
            f"falling back to {DEFAULT_LOG_LEVEL}",
            file=sys.stderr,
        )
        validated_level = getattr(logging, DEFAULT_LOG_LEVEL)

    return validated_level


def get_logger(file: str) -> logging.Logger:
    return logging.getLogger(f"{DEFAULT_LOGGER_NAME}.{Path(file).stem}")


@lru_cache
def setup_logging() -> dict[t.Any, t.Any]:
    handler = "console"
    log_level = resolve_log_level()
    if sys.stderr.isatty() and not os.environ.get(
        LIGHTSPEED_STACK_DISABLE_RICH_HANDLER_ENV_VAR
    ):
        handler = "rich"

    logging_conf = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            # RichHandler needs format="%(message)s" to prevent double-formatting by the root Formatter.
            "rich": {
                "format": "RICH %(message)s",
                "datefmt": "[%X]",
            },
            "console": {
                "format": DEFAULT_LOG_FORMAT,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "formatter": "console",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stderr",
            },
            "rich": {
                "formatter": "rich",
                "class": "rich.logging.RichHandler",
            },
        },
        "loggers": {
            DEFAULT_LOGGER_NAME: {
                "handlers": [handler],
                "level": log_level,
                "propagate": False,
            },
        },
    }

    merged_config = deep_update(uvicorn.config.LOGGING_CONFIG, logging_conf)
    merged_config["formatters"]["access"]["fmt"] = (
        '%(asctime)s.%(msecs)03d %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s'
    )
    merged_config["formatters"]["default"]["fmt"] = (
        "%(asctime)s.%(msecs)03d %(levelprefix)s%(message)s"
    )
    logging.config.dictConfig(merged_config)

    return merged_config

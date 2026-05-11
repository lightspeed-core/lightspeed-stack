"""Log utilities."""

import logging
import logging.config
import os
import sys
import typing as t
from datetime import datetime
from functools import lru_cache

import uvicorn.config
from pydantic.v1.utils import deep_update
from rich.text import Text

from constants import (
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_LEVEL,
    DEFAULT_LOGGER_NAME,
    LIGHTSPEED_STACK_DISABLE_RICH_HANDLER_ENV_VAR,
    LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR,
)


def _ms_time_format(dt: datetime) -> Text:
    """Format datetime object with zero padded milliseconds."""
    return Text(dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{dt.microsecond // 1000:03d}")


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


def get_logger(name: str) -> logging.Logger:
    """Create a common logger for all modules in this package."""
    # FIXME: Remove the need for this function.
    #
    # Normally this is derived from the package name (__name__).
    #
    # Since this program is sometimes called from from the entrypoint and
    # sometimes called from src/lightspeed_stack.py, the value for __name__
    # does not contain a consistent root value.
    #
    # How the application is installed and run needs to be streamlined so that
    # __name__ provides the expected value in all cases.
    return logging.getLogger(f"{DEFAULT_LOGGER_NAME}.{name}")


@lru_cache
def setup_logging() -> dict[t.Any, t.Any]:
    """Create logging configuration."""
    handler = "default"
    log_level = resolve_log_level()
    if sys.stderr.isatty() and not os.environ.get(
        LIGHTSPEED_STACK_DISABLE_RICH_HANDLER_ENV_VAR
    ):
        handler = "rich"

    logging_conf = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "rich": {
                "()": "rich.logging.RichHandler",
                "show_time": True,
                "log_time_format": _ms_time_format,
                "level": log_level,
            },
        },
        "loggers": {
            DEFAULT_LOGGER_NAME: {
                "handlers": [handler],
                "level": log_level,
                "propagate": False,
            },
            "llama_stack_client": {
                "handlers": [handler],
                "level": log_level,
                "propagate": False,
            },
        },
    }

    merged_config = deep_update(uvicorn.config.LOGGING_CONFIG, logging_conf)

    if handler == "rich":
        merged_config["loggers"]["uvicorn"]["handlers"] = [handler]
        merged_config["loggers"]["uvicorn.access"]["handlers"] = [handler]
    else:
        merged_config["formatters"]["access"]["fmt"] = (
            "%(asctime)s.%(msecs)03d %(levelprefix)s "
            '%(client_addr)s - "%(request_line)s" %(status_code)s'
        )
        merged_config["formatters"]["default"]["fmt"] = DEFAULT_LOG_FORMAT
        merged_config["formatters"]["default"]["datefmt"] = "%Y-%m-%d %H:%M:%S"

    logging.config.dictConfig(merged_config)

    return merged_config

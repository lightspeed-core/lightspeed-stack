"""Log utilities."""

import logging
import logging.config
import os
import sys
import typing as t
from copy import deepcopy
from datetime import datetime

import uvicorn.config
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


def _deep_merge(
    mapping: dict[t.Any, t.Any], updates: dict[t.Any, t.Any]
) -> dict[t.Any, t.Any]:
    """Recursively merge updates into mapping."""
    merged = mapping.copy()
    for k, v in updates.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v

    return merged


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
    # The need for this function should be removed in the future.
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


def build_logging_config() -> dict[t.Any, t.Any]:
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
            "ogx_client": {
                "handlers": [handler],
                "level": log_level,
                "propagate": False,
            },
        },
    }

    # Create a deep copy of uvicorn's logging config to avoid mutating global state.
    merged_config = _deep_merge(deepcopy(uvicorn.config.LOGGING_CONFIG), logging_conf)

    if handler == "rich":
        merged_config["loggers"]["uvicorn"]["handlers"] = [handler]
        merged_config["loggers"]["uvicorn.access"]["handlers"] = [handler]
    else:
        merged_config["formatters"]["access"]["fmt"] = (
            "%(asctime)s.%(msecs)03d %(levelprefix)s "
            '%(client_addr)s - "%(request_line)s" %(status_code)s'
        )
        merged_config["formatters"]["access"]["datefmt"] = "%Y-%m-%d %H:%M:%S"
        merged_config["formatters"]["default"]["fmt"] = DEFAULT_LOG_FORMAT
        merged_config["formatters"]["default"]["datefmt"] = "%Y-%m-%d %H:%M:%S"

    return merged_config


def setup_logging() -> None:
    """Set up main logging configuration."""
    logging.config.dictConfig(build_logging_config())

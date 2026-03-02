"""Log utilities."""

import logging
import os
import sys

from rich.logging import RichHandler

from constants import (
    LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR,
    DEFAULT_LOG_LEVEL,
    DEFAULT_LOG_FORMAT,
)


def resolve_log_level() -> int:
    """
    Resolve and validate the log level from environment variable.

    Reads the LIGHTSPEED_STACK_LOG_LEVEL environment variable and validates
    it against Python's logging module. If the environment variable is not set,
    defaults to DEFAULT_LOG_LEVEL. If the value is invalid, logs a warning and
    falls back to DEFAULT_LOG_LEVEL.

    Parameters:
        None

    Returns:
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


def create_log_handler() -> logging.Handler:
    """
    Create and return a configured log handler based on TTY availability.

    If stderr is connected to a terminal (TTY), returns a RichHandler for
    rich-formatted console output. Otherwise, returns a StreamHandler with
    plain-text formatting suitable for non-TTY environments (e.g., containers).

    Parameters:
        None

    Returns:
        logging.Handler: A configured handler instance (RichHandler or StreamHandler).
    """
    if sys.stderr.isatty():
        # RichHandler's columnar layout assumes a real terminal.
        # RichHandler handles its own formatting, so no formatter is set.
        return RichHandler()

    # In containers without a TTY, Rich falls back to 80 columns and
    # the columns consume most of that width, leaving ~40 chars for the actual message.
    # Tracebacks become nearly unreadable. Use a plain StreamHandler instead.
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))
    return handler


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger configured for Rich console output.

    The returned logger has its level set based on the LIGHTSPEED_STACK_LOG_LEVEL
    environment variable (defaults to INFO), its handlers replaced with a single
    handler (RichHandler for TTY or StreamHandler for non-TTY), and propagation
    to ancestor loggers disabled.

    Parameters:
        name (str): Name of the logger to retrieve or create.

    Returns:
        logging.Logger: The configured logger instance.
    """
    logger = logging.getLogger(name)

    # Skip reconfiguration if logger already has handlers from a prior call
    if logger.handlers:
        return logger

    logger.handlers = [create_log_handler()]
    logger.propagate = False
    logger.setLevel(resolve_log_level())
    return logger

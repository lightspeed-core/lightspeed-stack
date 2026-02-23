"""Log utilities."""

import logging
import os
import sys

from rich.logging import RichHandler

from constants import LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, DEFAULT_LOG_LEVEL


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger configured for Rich console output.

    The returned logger has its level set based on the LIGHTSPEED_STACK_LOG_LEVEL
    environment variable (defaults to INFO), its handlers replaced with a single
    RichHandler for rich-formatted console output, and propagation to ancestor
    loggers disabled.

    Parameters:
        name (str): Name of the logger to retrieve or create.

    Returns:
        logging.Logger: The configured logger instance.
    """
    logger = logging.getLogger(name)

    # Skip reconfiguration if logger already has handlers from a prior call
    if logger.handlers:
        return logger

    # RichHandler's columnar layout (timestamp, level, right-aligned filename) assumes
    # a real terminal. In containers without a TTY, Rich falls back to 80 columns and
    # the columns consume most of that width, leaving ~40 chars for the actual message.
    # Tracebacks become nearly unreadable. Use a plain StreamHandler when there's no TTY.
    if sys.stderr.isatty():
        logger.handlers = [RichHandler()]
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d %(message)s"
            )
        )
        logger.handlers = [handler]
    logger.propagate = False

    # Read log level from environment variable with default fallback
    level_str = os.environ.get(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, DEFAULT_LOG_LEVEL)

    # Validate the level string and convert to logging level constant
    validated_level = getattr(logging, level_str.upper(), None)
    if not isinstance(validated_level, int):
        logger.warning(
            "Invalid log level '%s', falling back to %s",
            level_str,
            DEFAULT_LOG_LEVEL,
        )
        validated_level = getattr(logging, DEFAULT_LOG_LEVEL)

    logger.setLevel(validated_level)
    return logger

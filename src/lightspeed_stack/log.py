"""Log utilities."""

import logging
from rich.logging import RichHandler


def get_logger(name: str) -> logging.Logger:
    """Retrieve logger with the provided name."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers = [RichHandler()]
    logger.propagate = False
    return logger

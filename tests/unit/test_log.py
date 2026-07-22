"""Unit tests for functions defined in src/log.py."""

import logging

import pytest

from lightspeed_stack.constants import (
    DEFAULT_LOGGER_NAME,
    LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR,
)
from lightspeed_stack.log import get_logger, resolve_log_level, setup_logging


def test_get_logger() -> None:
    """Check the function to retrieve logger."""
    setup_logging()

    logger = get_logger(__name__)

    assert logger is not None
    assert logger.name == f"{DEFAULT_LOGGER_NAME}.tests.unit.test_log"
    assert logger.hasHandlers()


def test_get_logger_invalid_env_var_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that invalid env var value falls back to INFO level."""
    monkeypatch.setenv(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, "FOOBAR")

    setup_logging()

    logger = get_logger(__name__)
    assert logger.getEffectiveLevel() == logging.INFO


@pytest.mark.parametrize(
    "level_name,expected_level",
    [
        ("DEBUG", logging.DEBUG),
        ("debug", logging.DEBUG),
        ("INFO", logging.INFO),
        ("info", logging.INFO),
        ("WARNING", logging.WARNING),
        ("warning", logging.WARNING),
        ("ERROR", logging.ERROR),
        ("error", logging.ERROR),
        ("CRITICAL", logging.CRITICAL),
        ("critical", logging.CRITICAL),
    ],
)
def test_get_logger_log_level(
    monkeypatch: pytest.MonkeyPatch, level_name: str, expected_level: int
) -> None:
    """Test that all valid log levels work correctly, case-insensitively.

    Verifies that setting the log-level environment variable
    produces a logger with the corresponding numeric level,
    matching level names case-insensitively.
    """
    monkeypatch.setenv(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, level_name)

    setup_logging()

    logger = get_logger(__name__)
    assert logger.getEffectiveLevel() == expected_level


def test_get_logger_default_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that get_logger() uses INFO level by default when env var is not set."""
    monkeypatch.delenv(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, raising=False)

    setup_logging()

    logger = get_logger(__name__)
    assert logger.getEffectiveLevel() == logging.INFO


@pytest.mark.parametrize(
    ("level_name", "expected_level"),
    [
        ("DEBUG", logging.DEBUG),
        ("debug", logging.DEBUG),
        ("INFO", logging.INFO),
        ("WARNING", logging.WARNING),
        ("ERROR", logging.ERROR),
        ("CRITICAL", logging.CRITICAL),
        ("critical", logging.CRITICAL),
    ],
)
def test_resolve_log_level(
    monkeypatch: pytest.MonkeyPatch, level_name: str, expected_level: int
) -> None:
    """Test that resolve_log_level correctly resolves valid level names."""
    monkeypatch.setenv(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, level_name)

    setup_logging()

    assert resolve_log_level() == expected_level


def test_resolve_log_level_invalid_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that resolve_log_level falls back to INFO for invalid values."""
    monkeypatch.setenv(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, "BOGUS")

    setup_logging()

    assert resolve_log_level() == logging.INFO


def test_resolve_log_level_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that resolve_log_level defaults to INFO when env var is unset."""
    monkeypatch.delenv(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, raising=False)

    setup_logging()

    assert resolve_log_level() == logging.INFO

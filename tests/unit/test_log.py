"""Unit tests for functions defined in src/log.py."""

import logging

import pytest
from pytest_mock import MockerFixture
from rich.logging import RichHandler

from log import get_logger, resolve_log_level, create_log_handler
from constants import LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, DEFAULT_LOG_FORMAT


def test_get_logger() -> None:
    """Check the function to retrieve logger."""
    logger_name = "foo"
    logger = get_logger(logger_name)
    assert logger is not None
    assert logger.name == logger_name

    # at least one handler need to be set
    assert len(logger.handlers) >= 1


def test_get_logger_invalid_env_var_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that invalid env var value falls back to INFO level."""
    monkeypatch.setenv(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, "FOOBAR")

    logger = get_logger("test_invalid")
    assert logger.level == logging.INFO


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
    """Test that all valid log levels work correctly, case-insensitively."""
    monkeypatch.setenv(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, level_name)

    logger = get_logger(f"test_{level_name}")
    assert logger.level == expected_level


def test_get_logger_default_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that get_logger() uses INFO level by default when env var is not set."""
    monkeypatch.delenv(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, raising=False)

    logger = get_logger("test_default")
    assert logger.level == logging.INFO


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
    assert resolve_log_level() == expected_level


def test_resolve_log_level_invalid_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that resolve_log_level falls back to INFO for invalid values."""
    monkeypatch.setenv(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, "BOGUS")
    assert resolve_log_level() == logging.INFO


def test_resolve_log_level_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that resolve_log_level defaults to INFO when env var is unset."""
    monkeypatch.delenv(LIGHTSPEED_STACK_LOG_LEVEL_ENV_VAR, raising=False)
    assert resolve_log_level() == logging.INFO


def test_create_log_handler_tty(mocker: MockerFixture) -> None:
    """Test that create_log_handler returns RichHandler when TTY is available."""
    mocker.patch("sys.stderr.isatty", return_value=True)
    handler = create_log_handler()
    assert isinstance(handler, RichHandler)


def test_create_log_handler_non_tty(mocker: MockerFixture) -> None:
    """Test that create_log_handler returns StreamHandler when no TTY."""
    mocker.patch("sys.stderr.isatty", return_value=False)
    handler = create_log_handler()
    assert isinstance(handler, logging.StreamHandler)
    assert not isinstance(handler, RichHandler)


def test_create_log_handler_non_tty_format(mocker: MockerFixture) -> None:
    """Test that non-TTY handler uses DEFAULT_LOG_FORMAT."""
    mocker.patch("sys.stderr.isatty", return_value=False)
    handler = create_log_handler()
    assert handler.formatter is not None
    # pylint: disable=protected-access
    assert handler.formatter._fmt == DEFAULT_LOG_FORMAT

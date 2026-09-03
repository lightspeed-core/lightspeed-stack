"""Unit tests for Splunk HEC client."""

import asyncio
from collections.abc import Generator
from pathlib import Path
from typing import Any, Optional

import aiohttp
import pytest
from pytest_mock import MockerFixture

from observability.splunk import (
    _cleanup_fire_and_forget_task,
    _fire_and_forget_tasks,
    _read_token_from_file,
    dispatch_splunk_event,
    send_splunk_event,
)


@pytest.fixture(name="mock_splunk_config")
def mock_splunk_config_fixture(tmp_path: Path, mocker: MockerFixture) -> Any:
    """Create a mock SplunkConfiguration.

    Create a mocked Splunk configuration object for tests.

    The returned mock has attributes pre-populated to simulate a valid Splunk HEC configuration:
    - enabled = True
    - url = "https://splunk.example.com:8088/services/collector"
    - token_path = Path to a temporary file containing "test-hec-token"
    - index = "test_index"
    - source = "test-source"
    - timeout = 5
    - verify_ssl = True

    Returns:
        mock_config: A MagicMock configured with the above Splunk fields.
    """
    token_file = tmp_path / "token"
    token_file.write_text("test-hec-token")

    config = mocker.MagicMock()
    config.enabled = True
    config.url = "https://splunk.example.com:8088/services/collector"
    config.token_path = token_file
    config.index = "test_index"
    config.source = "test-source"
    config.timeout = 5
    config.verify_ssl = True
    return config


@pytest.fixture(name="mock_session")
def mock_session_fixture(mocker: MockerFixture) -> Any:
    """Create a mock aiohttp session with successful response.

    Parameters:
        - mocker (pytest_mock.MockerFixture): Fixture used to create AsyncMock objects.

    Returns:
        AsyncMock: A mock session (`spec=aiohttp.ClientSession`) whose `post()`
        returns an async context manager that yields a response mock with
        `status = 200`.
    """
    mock_response = mocker.AsyncMock()
    mock_response.status = 200
    session = mocker.AsyncMock(spec=aiohttp.ClientSession)
    session.post.return_value.__aenter__.return_value = mock_response
    return session


@pytest.mark.parametrize(
    ("token_content", "expected"),
    [
        ("  my-secret-token  \n", "my-secret-token"),
        ("token-no-whitespace", "token-no-whitespace"),
    ],
    ids=["strips_whitespace", "no_whitespace"],
)
def test_read_token_from_file(
    tmp_path: Path, token_content: str, expected: str
) -> None:
    """Test reading and stripping token from file."""
    token_file = tmp_path / "token"
    token_file.write_text(token_content)
    assert _read_token_from_file(str(token_file)) == expected


def test_read_token_returns_none_for_missing_file(tmp_path: Path) -> None:
    """Test returns None when file doesn't exist."""
    assert _read_token_from_file(str(tmp_path / "nonexistent")) is None


def _make_config(
    mocker: MockerFixture,
    enabled: bool = True,
    url: Optional[str] = "https://splunk:8088",
    token_path: Optional[Path] = None,
    index: Optional[str] = "idx",
) -> Any:
    """Helper to create mock config with specific fields."""
    config = mocker.MagicMock()
    config.enabled = enabled
    config.url = url
    config.token_path = token_path
    config.index = index
    return config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("splunk_config",),
    [
        (None,),
        ("disabled",),
        ("incomplete",),
    ],
    ids=["config_none", "disabled", "incomplete"],
)
async def test_skips_event_when_not_configured(
    mocker: MockerFixture, splunk_config: Any
) -> None:
    """Test event is skipped when Splunk is not properly configured."""
    if splunk_config == "disabled":
        splunk_config = _make_config(mocker, enabled=False)
    elif splunk_config == "incomplete":
        splunk_config = _make_config(mocker, url=None, index=None)

    mock_config = mocker.patch("observability.splunk.configuration")
    mock_config.splunk = splunk_config
    # Should not raise, just skip silently
    await send_splunk_event({"test": "event"}, "test_sourcetype")


@pytest.mark.asyncio
async def test_sends_event_successfully(
    mocker: MockerFixture,
    mock_splunk_config: Any,
    mock_session: Any,
) -> None:
    """Test event is sent successfully to Splunk HEC."""
    mock_config = mocker.patch("observability.splunk.configuration")
    mock_config.splunk = mock_splunk_config
    mock_client = mocker.patch("observability.splunk.aiohttp.ClientSession")
    mock_client.return_value.__aenter__.return_value = mock_session

    await send_splunk_event({"question": "test"}, "infer_with_llm")

    mock_session.post.assert_called_once()
    call_args = mock_session.post.call_args
    assert call_args[0][0] == mock_splunk_config.url
    assert "Authorization" in call_args[1]["headers"]
    assert call_args[1]["json"]["sourcetype"] == "infer_with_llm"
    assert call_args[1]["json"]["event"] == {"question": "test"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_setup",),
    [
        (
            lambda s: setattr(
                s.post.return_value.__aenter__.return_value, "status", 503
            ),
        ),
        (
            lambda s: setattr(
                s.return_value.__aenter__, "side_effect", aiohttp.ClientError()
            ),
        ),
    ],
    ids=["http_error", "client_error"],
)
async def test_logs_warning_on_error(
    mocker: MockerFixture,
    mock_splunk_config: Any,
    error_setup: Any,
) -> None:
    """Test warning is logged on HTTP or client errors."""
    mock_session = mocker.AsyncMock(spec=aiohttp.ClientSession)
    mock_response = mocker.AsyncMock()
    mock_response.status = 503
    mock_response.text.return_value = "error"
    mock_session.post.return_value.__aenter__.return_value = mock_response

    mock_config = mocker.patch("observability.splunk.configuration")
    mock_config.splunk = mock_splunk_config
    mock_client = mocker.patch("observability.splunk.aiohttp.ClientSession")
    error_setup(mock_client)
    mock_client.return_value.__aenter__.return_value = mock_session
    mock_logger = mocker.patch("observability.splunk.logger")

    await send_splunk_event({"test": "event"}, "test_sourcetype")

    mock_logger.warning.assert_called()


# ---------------------------------------------------------------------------
# dispatch_splunk_event tests
# ---------------------------------------------------------------------------


class TestDispatchSplunkEvent:
    """Tests for the dispatch_splunk_event dispatcher function."""

    @pytest.fixture(autouse=True)
    def _cleanup_fire_and_forget(self) -> Generator[None, None, None]:
        """Ensure _fire_and_forget_tasks is cleaned after each test."""
        yield
        _fire_and_forget_tasks.clear()

    def test_noop_when_no_dispatch_method(self, mocker: MockerFixture) -> None:
        """No-op when background_tasks is None and fire_and_forget is False."""
        mock_send = mocker.patch("observability.splunk.send_splunk_event")
        mock_create_task = mocker.patch("observability.splunk.asyncio.create_task")

        dispatch_splunk_event({"k": "v"}, "test_sourcetype")

        mock_send.assert_not_called()
        mock_create_task.assert_not_called()

    def test_dispatches_via_background_tasks(self, mocker: MockerFixture) -> None:
        """Queues send_splunk_event via BackgroundTasks when provided."""
        mock_bg = mocker.MagicMock()

        dispatch_splunk_event({"k": "v"}, "test_sourcetype", background_tasks=mock_bg)

        mock_bg.add_task.assert_called_once_with(
            send_splunk_event, {"k": "v"}, "test_sourcetype"
        )

    def test_dispatches_fire_and_forget(self, mocker: MockerFixture) -> None:
        """Creates asyncio task and registers it for GC protection."""
        sentinel_task = mocker.MagicMock()
        mock_create_task = mocker.patch(
            "observability.splunk.asyncio.create_task", return_value=sentinel_task
        )
        # Prevent real coroutine creation; the mock returns a coroutine-like
        # object that create_task can accept.
        mocker.patch("observability.splunk.send_splunk_event")

        dispatch_splunk_event({"k": "v"}, "test_sourcetype", fire_and_forget=True)

        mock_create_task.assert_called_once()
        assert sentinel_task in _fire_and_forget_tasks
        sentinel_task.add_done_callback.assert_called_once_with(
            _cleanup_fire_and_forget_task
        )

    def test_fire_and_forget_takes_priority(self, mocker: MockerFixture) -> None:
        """When both background_tasks and fire_and_forget are set, fire-and-forget wins."""
        mock_bg = mocker.MagicMock()
        sentinel_task = mocker.MagicMock()
        mocker.patch(
            "observability.splunk.asyncio.create_task", return_value=sentinel_task
        )
        mocker.patch("observability.splunk.send_splunk_event")

        dispatch_splunk_event(
            {"k": "v"},
            "test_sourcetype",
            background_tasks=mock_bg,
            fire_and_forget=True,
        )

        mock_bg.add_task.assert_not_called()
        assert sentinel_task in _fire_and_forget_tasks


# ---------------------------------------------------------------------------
# _cleanup_fire_and_forget_task tests
# ---------------------------------------------------------------------------


class TestCleanupFireAndForgetTask:
    """Tests for the fire-and-forget done-callback."""

    @pytest.fixture(autouse=True)
    def _cleanup_fire_and_forget(self) -> Generator[None, None, None]:
        """Ensure _fire_and_forget_tasks is cleaned after each test."""
        yield
        _fire_and_forget_tasks.clear()

    def test_discards_task_on_success(self, mocker: MockerFixture) -> None:
        """Successful task is removed from tracking set."""
        task = mocker.MagicMock()
        task.result.return_value = None
        _fire_and_forget_tasks.add(task)

        _cleanup_fire_and_forget_task(task)

        assert task not in _fire_and_forget_tasks

    def test_logs_debug_on_cancellation(self, mocker: MockerFixture) -> None:
        """Cancelled task logs at debug level and is removed."""
        task = mocker.MagicMock()
        task.result.side_effect = asyncio.CancelledError()
        _fire_and_forget_tasks.add(task)
        mock_logger = mocker.patch("observability.splunk.logger")

        _cleanup_fire_and_forget_task(task)

        assert task not in _fire_and_forget_tasks
        mock_logger.debug.assert_called_once()

    def test_logs_warning_on_exception(self, mocker: MockerFixture) -> None:
        """Failed task logs warning with exc_info and is removed."""
        task = mocker.MagicMock()
        task.result.side_effect = RuntimeError("connection refused")
        _fire_and_forget_tasks.add(task)
        mock_logger = mocker.patch("observability.splunk.logger")

        _cleanup_fire_and_forget_task(task)

        assert task not in _fire_and_forget_tasks
        mock_logger.warning.assert_called_once_with(
            "Splunk fire-and-forget task failed", exc_info=True
        )

"""Unit tests for Splunk HEC client."""

from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from observability.splunk import send_splunk_event, _read_token_from_file


@pytest.fixture(name="mock_splunk_config")
def mock_splunk_config_fixture(tmp_path: Path) -> MagicMock:
    """Create a mock SplunkConfiguration."""
    token_file = tmp_path / "token"
    token_file.write_text("test-hec-token")

    config = MagicMock()
    config.enabled = True
    config.url = "https://splunk.example.com:8088/services/collector"
    config.token_path = token_file
    config.index = "test_index"
    config.source = "test-source"
    config.timeout = 5
    config.verify_ssl = True
    return config


@pytest.fixture(name="mock_session")
def mock_session_fixture() -> AsyncMock:
    """Create a mock aiohttp session with successful response."""
    mock_response = AsyncMock()
    mock_response.status = 200
    session = AsyncMock(spec=aiohttp.ClientSession)
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
    enabled: bool = True,
    url: Optional[str] = "https://splunk:8088",
    token_path: Optional[Path] = None,
    index: Optional[str] = "idx",
) -> MagicMock:
    """Helper to create mock config with specific fields."""
    config = MagicMock()
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
        (_make_config(enabled=False),),
        (_make_config(url=None, index=None),),
    ],
    ids=["config_none", "disabled", "incomplete"],
)
async def test_skips_event_when_not_configured(splunk_config: Any) -> None:
    """Test event is skipped when Splunk is not properly configured."""
    with patch("observability.splunk.configuration") as mock_config:
        mock_config.splunk = splunk_config
        # Should not raise, just skip silently
        await send_splunk_event({"test": "event"}, "test_sourcetype")


@pytest.mark.asyncio
async def test_sends_event_successfully(
    mock_splunk_config: MagicMock, mock_session: AsyncMock
) -> None:
    """Test event is sent successfully to Splunk HEC."""
    with (
        patch("observability.splunk.configuration") as mock_config,
        patch("observability.splunk.aiohttp.ClientSession") as mock_client,
    ):
        mock_config.splunk = mock_splunk_config
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
    mock_splunk_config: MagicMock, error_setup: Any
) -> None:
    """Test warning is logged on HTTP or client errors."""
    mock_session = AsyncMock(spec=aiohttp.ClientSession)
    mock_response = AsyncMock()
    mock_response.status = 503
    mock_response.text.return_value = "error"
    mock_session.post.return_value.__aenter__.return_value = mock_response

    with (
        patch("observability.splunk.configuration") as mock_config,
        patch("observability.splunk.aiohttp.ClientSession") as mock_client,
        patch("observability.splunk.logger") as mock_logger,
    ):
        mock_config.splunk = mock_splunk_config
        error_setup(mock_client)
        mock_client.return_value.__aenter__.return_value = mock_session

        await send_splunk_event({"test": "event"}, "test_sourcetype")

        mock_logger.warning.assert_called()

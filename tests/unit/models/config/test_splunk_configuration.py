"""Unit tests for SplunkConfiguration model."""

from pathlib import Path

from typing import Optional

import pytest

from models.config import SplunkConfiguration


@pytest.fixture(name="token_file")
def token_file_fixture(tmp_path: Path) -> Path:
    """Create a temporary token file for testing."""
    token_file = tmp_path / "token"
    token_file.write_text("test-token")
    return token_file


def test_default_values() -> None:
    """Test default SplunkConfiguration has expected values."""
    cfg = SplunkConfiguration()  # pyright: ignore[reportCallIssue]
    assert cfg.enabled is False
    assert cfg.url is None
    assert cfg.token_path is None
    assert cfg.index is None
    assert cfg.source == "lightspeed-stack"
    assert cfg.timeout == 5
    assert cfg.verify_ssl is True


def test_disabled_skips_validation() -> None:
    """Test that disabled Splunk config doesn't require other fields."""
    cfg = SplunkConfiguration(enabled=False)  # pyright: ignore[reportCallIssue]
    assert cfg.enabled is False
    assert cfg.url is None


@pytest.mark.parametrize(
    ("url", "has_token", "index", "expected_missing"),
    [
        (None, False, None, r"url.*token_path.*index"),
        ("https://splunk:8088", False, None, r"token_path.*index"),
        ("https://splunk:8088", False, "idx", r"token_path"),
        ("https://splunk:8088", True, None, r"index"),
        (None, True, "idx", r"url"),
    ],
    ids=[
        "all_missing",
        "url_present_only",
        "url_and_index_present",
        "url_and_token_present",
        "token_and_index_present",
    ],
)
def test_enabled_missing_required_fields(
    token_file: Path,
    url: Optional[str],
    has_token: bool,
    index: Optional[str],
    expected_missing: str,
) -> None:
    """Test that enabled Splunk config validates required fields."""
    with pytest.raises(ValueError, match=expected_missing):
        SplunkConfiguration(
            enabled=True,
            url=url,
            token_path=token_file if has_token else None,
            index=index,
        )  # pyright: ignore[reportCallIssue]


def test_valid_enabled_configuration(token_file: Path) -> None:
    """Test valid enabled Splunk configuration passes validation."""
    cfg = SplunkConfiguration(
        enabled=True,
        url="https://splunk.example.com:8088",
        token_path=token_file,
        index="rhel_lightspeed",
        source="my-service",
        timeout=10,
        verify_ssl=False,
    )

    assert cfg.enabled is True
    assert cfg.url == "https://splunk.example.com:8088"
    assert cfg.token_path == token_file
    assert cfg.index == "rhel_lightspeed"
    assert cfg.source == "my-service"
    assert cfg.timeout == 10
    assert cfg.verify_ssl is False


def test_custom_source() -> None:
    """Test custom source value is preserved."""
    cfg = SplunkConfiguration(
        enabled=False, source="custom-source"
    )  # pyright: ignore[reportCallIssue]
    assert cfg.source == "custom-source"


def test_custom_timeout() -> None:
    """Test custom timeout value is preserved."""
    cfg = SplunkConfiguration(
        enabled=False, timeout=30
    )  # pyright: ignore[reportCallIssue]
    assert cfg.timeout == 30


def test_verify_ssl_disabled() -> None:
    """Test verify_ssl can be disabled."""
    cfg = SplunkConfiguration(
        enabled=False, verify_ssl=False
    )  # pyright: ignore[reportCallIssue]
    assert cfg.verify_ssl is False

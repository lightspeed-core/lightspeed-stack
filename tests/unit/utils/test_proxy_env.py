"""Unit tests for proxy environment helpers."""

import os

import httpx
import pytest

from utils.proxy_env import (
    is_unsupported_no_proxy_entry,
    sanitize_no_proxy_env,
    sanitize_no_proxy_value,
)


class TestIsUnsupportedNoProxyEntry:
    """Tests for is_unsupported_no_proxy_entry."""

    @pytest.mark.parametrize(
        "entry",
        [
            "fd00:1234:5678::/64",
            "fd01::/48",
            "fd02::/112",
        ],
    )
    def test_ipv6_cidr_entries_are_unsupported(self, entry: str) -> None:
        """IPv6 CIDR entries should be treated as unsupported."""
        assert is_unsupported_no_proxy_entry(entry) is True

    @pytest.mark.parametrize(
        "entry",
        [
            "localhost",
            "127.0.0.0/8",
            "10.0.0.0/8",
            ".cluster.local",
            ".svc",
        ],
    )
    def test_common_entries_remain_supported(self, entry: str) -> None:
        """Common OpenShift NO_PROXY entries should be preserved."""
        assert is_unsupported_no_proxy_entry(entry) is False


class TestSanitizeNoProxyValue:
    """Tests for sanitize_no_proxy_value."""

    def test_removes_only_ipv6_cidr_entries(self) -> None:
        """Sanitization should keep supported entries and drop IPv6 CIDRs."""
        original = (
            "localhost,127.0.0.0/8,fd00:1234:5678::/64,fd01::/48,"
            "fd02::/112,.cluster.local,.svc"
        )

        sanitized, removed = sanitize_no_proxy_value(original)

        assert sanitized == "localhost,127.0.0.0/8,.cluster.local,.svc"
        assert removed == [
            "fd00:1234:5678::/64",
            "fd01::/48",
            "fd02::/112",
        ]


class TestSanitizeNoProxyEnv:
    """Tests for sanitize_no_proxy_env."""

    def test_updates_both_proxy_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Both NO_PROXY and no_proxy should be sanitized."""
        monkeypatch.setenv(
            "NO_PROXY",
            "localhost,fd00:1234:5678::/64,.cluster.local",
        )
        monkeypatch.setenv("no_proxy", "localhost,fd01::/48")

        removed = sanitize_no_proxy_env()

        assert removed == ["fd00:1234:5678::/64", "fd01::/48"]
        assert os.environ["NO_PROXY"] == "localhost,.cluster.local"
        assert os.environ["no_proxy"] == "localhost"

    def test_httpx_client_initializes_after_sanitize(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """httpx should not crash once unsupported entries are removed."""
        monkeypatch.setenv(
            "NO_PROXY",
            "localhost,fd00:1234:5678::/64,fd01::/48,fd02::/112",
        )

        sanitize_no_proxy_env()

        with httpx.Client() as client:
            assert client is not None

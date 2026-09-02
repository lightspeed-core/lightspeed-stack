"""Helpers for normalizing proxy-related environment variables."""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

_NO_PROXY_ENV_VARS = ("NO_PROXY", "no_proxy")

# IPv6 CIDR entries (for example fd00:1234:5678::/64) crash httpx until
# https://github.com/encode/httpx/pull/3741 ships in a release.
_IPV6_CIDR_PATTERN = re.compile(r"::.*/")


def is_unsupported_no_proxy_entry(entry: str) -> bool:
    """Return True when a NO_PROXY entry cannot be parsed by httpx."""
    stripped = entry.strip()
    if not stripped:
        return True
    return _IPV6_CIDR_PATTERN.search(stripped) is not None


def sanitize_no_proxy_value(value: str) -> tuple[str, list[str]]:
    """Remove unsupported NO_PROXY entries from a comma-separated value."""
    kept: list[str] = []
    removed: list[str] = []

    for entry in value.split(","):
        stripped = entry.strip()
        if not stripped:
            continue
        if is_unsupported_no_proxy_entry(stripped):
            removed.append(stripped)
        else:
            kept.append(stripped)

    return ",".join(kept), removed


def sanitize_no_proxy_env() -> list[str]:
    """Sanitize NO_PROXY/no_proxy before httpx reads proxy settings.

    OpenShift cluster proxies commonly inject IPv6 CIDR bypass entries.
    httpx currently mis-parses those values and raises InvalidURL during
    client initialization (encode/httpx#3221).

    Returns:
        Entries removed from the environment.
    """
    removed: list[str] = []

    for var in _NO_PROXY_ENV_VARS:
        value = os.environ.get(var)
        if value is None:
            continue

        sanitized, removed_entries = sanitize_no_proxy_value(value)
        removed.extend(removed_entries)

        if sanitized:
            os.environ[var] = sanitized
        else:
            os.environ.pop(var, None)

    if removed:
        logger.warning(
            "Removed unsupported IPv6 CIDR entries from NO_PROXY/no_proxy "
            "to avoid httpx startup failures: %s",
            ", ".join(removed),
        )

    return removed

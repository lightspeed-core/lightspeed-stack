"""Fixes applied to OGX code when it runs inside this process (LCORE-4782).

In library mode OGX handles a request in the task of the endpoint that called
it, so a fault in how OGX leaves its cancel scopes lands in that task.

OGX opens one MCP client session per MCP server a request uses and closes them
all at the end of the request, in the order it opened them
(``MCPSessionManager.__aexit__``). Each session holds two anyio cancel scopes,
and anyio only lets a task leave cancel scopes in the reverse order of entering
them. With two or more MCP servers in a request the first session's exit fails,
OGX swallows that failure, and the task keeps cancel scopes it never leaves.
The next cancel scope the task leaves raises ``RuntimeError: Attempted to exit a
cancel scope that isn't the current task's current cancel scope``, and when a
dangling scope was cancelled first, the task's next ``await`` is cancelled
instead. ``/v1/query`` then answers 500 after the model has answered, and in
``/v1/responses`` the topic summary call that follows the completed turn is
cancelled.

The fix is to close the sessions newest first, so the scopes are left in the
right order. Until OGX does that itself, :func:`apply_ogx_library_patches`
replaces the method with :func:`close_mcp_sessions_newest_first`, which is the
same code with the loop reversed. The replacement is only made when the
shipped method still has the shape the patch was written for, so a future OGX
that changes or fixes the method is left alone. OGX running as a separate
service has the same fault on its own side; this module cannot reach it.
"""

import inspect
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Final

from ogx.providers.utils.tools import mcp as ogx_mcp
from semver import Version

from log import get_logger

logger = get_logger(__name__)

SHIPPED_MCP_SESSION_EXIT: Final = ogx_mcp.MCPSessionManager.__aexit__
"""The ``MCPSessionManager.__aexit__`` OGX ships, kept for the tests and the checks."""

LAST_OGX_VERSION_CLOSING_SESSIONS_OLDEST_FIRST: Final[str] = "1.2.5"
"""The newest OGX version seen closing MCP sessions in the order they were opened."""

_OLDEST_FIRST_LOOP: Final[str] = "in list(self._sessions.items()):"
_NEWEST_FIRST_MARK: Final[str] = "reversed("


async def close_mcp_sessions_newest_first(
    self: Any, exc_type: Any, exc_val: Any, exc_tb: Any
) -> bool:
    """Close the MCP sessions of a request, newest first.

    A drop-in replacement of ``MCPSessionManager.__aexit__``: the same closing
    code, iterating the sessions in reverse order of their creation so that
    each session leaves its cancel scopes while they are still the task's
    current ones.

    Parameters:
        self: The session manager being left.
        exc_type: Ignored, as in OGX.
        exc_val: Ignored, as in OGX.
        exc_tb: Ignored, as in OGX.

    Returns:
        False: an exception that ended the ``async with`` block propagates.

    """
    del exc_type, exc_val, exc_tb
    errors = 0
    sessions = list(self._sessions.items())  # pylint: disable=protected-access
    for key, (session, client_ctx, _) in reversed(sessions):
        for context in (session, client_ctx):
            try:
                await context.__aexit__(None, None, None)
            except (
                BaseException  # pylint: disable=broad-exception-caught  # noqa: BLE001
            ) as exc:
                # As in OGX: a cancellation during cleanup must not stop the
                # other sessions from closing.
                errors += 1
                logger.debug("Error closing MCP session %s: %s", key[:32], exc)
    self._sessions.clear()  # pylint: disable=protected-access
    self._locks.clear()  # pylint: disable=protected-access
    logger.debug(
        "Closed %d MCP sessions, %d of them with errors", len(sessions), errors
    )
    return False


def ogx_version() -> str | None:
    """Return the installed OGX version, or None when it cannot be read.

    Returns:
        The version string of the ``ogx`` distribution, or None.

    """
    try:
        return version("ogx")
    except PackageNotFoundError:
        return None


def _source_of(function: Any) -> str | None:
    """Return the source of ``function``, or None when it is not available.

    Parameters:
        function: The function to read.

    Returns:
        The source text, or None.

    """
    try:
        return inspect.getsource(function)
    except (OSError, TypeError):
        return None


def _closes_sessions_oldest_first(function: Any) -> bool:
    """Tell whether ``function`` is the teardown this patch was written for.

    Parameters:
        function: The current ``MCPSessionManager.__aexit__``.

    Returns:
        True when its source has the oldest-first loop, or, without source to
        read, when the OGX version is one known to have it.

    """
    source = _source_of(function)
    if source is not None:
        return _OLDEST_FIRST_LOOP in source and _NEWEST_FIRST_MARK not in source
    current = ogx_version()
    if current is None:
        return False
    return Version.parse(current) <= Version.parse(
        LAST_OGX_VERSION_CLOSING_SESSIONS_OLDEST_FIRST
    )


def _patch_mcp_session_teardown() -> None:
    """Make ``MCPSessionManager`` close its sessions newest first, if it does not yet."""
    manager = ogx_mcp.MCPSessionManager
    if manager.__aexit__ is close_mcp_sessions_newest_first:
        return
    if not _closes_sessions_oldest_first(manager.__aexit__):
        logger.warning(
            "Not patching the MCP session teardown of ogx %s: it is not the code "
            "the patch was written for. Check whether LCORE-4782 still applies.",
            ogx_version(),
        )
        return
    manager.__aexit__ = close_mcp_sessions_newest_first  # type: ignore[method-assign]
    logger.info(
        "Patched ogx %s to close the MCP sessions of a request newest first "
        "(LCORE-4782)",
        ogx_version(),
    )


def apply_ogx_library_patches() -> None:
    """Apply the fixes OGX needs when it runs in this process.

    Safe to call more than once.
    """
    _patch_mcp_session_teardown()

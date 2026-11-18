"""Unit tests for the fixes applied to OGX when it runs in this process (LCORE-4782)."""

from collections.abc import Iterator
from typing import Any

import anyio
import pytest
from ogx.providers.utils.tools import mcp as ogx_mcp
from pytest_mock import MockerFixture

from client import ogx_library_patches as patches


@pytest.fixture(autouse=True)
def restore_session_manager() -> Iterator[None]:
    """Leave ``MCPSessionManager`` as the test found it."""
    original = ogx_mcp.MCPSessionManager.__aexit__
    yield
    ogx_mcp.MCPSessionManager.__aexit__ = original  # type: ignore[method-assign]


class ScopedContext:
    """A context that holds an anyio cancel scope, like an MCP client or session.

    ``streamablehttp_client`` and ``ClientSession`` each run a task group, and
    a task group is a cancel scope that has to be left in the reverse order of
    entering it.
    """

    def __init__(self, name: str, closed: list[str], fail: bool = False) -> None:
        """Remember where to record the close and whether to fail it."""
        self.name = name
        self.closed = closed
        self.fail = fail
        self._scope = anyio.CancelScope()

    async def __aenter__(self) -> "ScopedContext":
        """Enter the cancel scope."""
        self._scope.__enter__()
        return self

    async def __aexit__(self, *exc: object) -> bool:
        """Record the close, then leave the cancel scope."""
        self.closed.append(self.name)
        if self.fail:
            raise ValueError(f"{self.name} refused to close")
        self._scope.__exit__(None, None, None)
        return False


async def open_sessions(
    manager: Any, names: list[str], closed: list[str], fail: str = ""
) -> None:
    """Open one fake MCP session per name, the way ``_create_session`` nests them."""
    for name in names:
        # Entered by hand, as OGX's _create_session does, so the test controls
        # the exit order.
        client = ScopedContext(f"client-{name}", closed)
        await client.__aenter__()  # pylint: disable=unnecessary-dunder-call
        session = ScopedContext(f"session-{name}", closed, fail=name == fail)
        await session.__aenter__()  # pylint: disable=unnecessary-dunder-call
        sessions = manager._sessions  # pylint: disable=protected-access
        sessions[name] = (session, client, session)


async def run_in_child_task(coro_fn: Any) -> None:
    """Run ``coro_fn`` in a task-group child, as pydantic-graph runs a node."""
    async with anyio.create_task_group() as task_group:
        task_group.start_soon(coro_fn)


@pytest.mark.asyncio
async def test_shipped_teardown_breaks_the_task_with_two_sessions() -> None:
    """OGX closes the sessions oldest first, which leaves the task's cancel scopes dangling."""
    manager = ogx_mcp.MCPSessionManager()
    closed: list[str] = []

    async def use_two_servers() -> None:
        await open_sessions(manager, ["a", "b"], closed)
        await patches.SHIPPED_MCP_SESSION_EXIT(manager, None, None, None)

    with pytest.raises(BaseExceptionGroup) as excinfo:
        await run_in_child_task(use_two_servers)

    assert excinfo.group_contains(RuntimeError, match="cancel scope")
    assert closed == ["session-a", "client-a", "session-b", "client-b"]


@pytest.mark.asyncio
async def test_shipped_teardown_is_fine_with_one_session() -> None:
    """With a single session the order does not matter, which is why one MCP server works."""
    manager = ogx_mcp.MCPSessionManager()
    closed: list[str] = []

    async def use_one_server() -> None:
        await open_sessions(manager, ["a"], closed)
        await patches.SHIPPED_MCP_SESSION_EXIT(manager, None, None, None)

    await run_in_child_task(use_one_server)

    assert closed == ["session-a", "client-a"]


@pytest.mark.asyncio
async def test_patched_teardown_closes_newest_first() -> None:
    """The patch leaves the scopes in reverse order, and the task ends cleanly."""
    manager = ogx_mcp.MCPSessionManager()
    closed: list[str] = []
    returned: list[bool] = []

    async def use_two_servers() -> None:
        await open_sessions(manager, ["a", "b"], closed)
        returned.append(
            await patches.close_mcp_sessions_newest_first(manager, None, None, None)
        )

    await run_in_child_task(use_two_servers)

    assert closed == ["session-b", "client-b", "session-a", "client-a"]
    assert returned == [False]
    assert not manager._sessions  # pylint: disable=protected-access
    assert not manager._locks  # pylint: disable=protected-access


@pytest.mark.asyncio
async def test_patched_teardown_closes_the_rest_when_one_close_fails() -> None:
    """A failing close is logged and does not stop the other sessions from closing."""
    manager = ogx_mcp.MCPSessionManager()
    closed: list[str] = []

    async def use_two_servers() -> None:
        await open_sessions(manager, ["a", "b"], closed, fail="b")
        await patches.close_mcp_sessions_newest_first(manager, None, None, None)

    # session-b never leaves its scope, so the task that opened it cannot end
    # cleanly either; the point is that a, opened before b, is still closed.
    with pytest.raises(BaseExceptionGroup):
        await run_in_child_task(use_two_servers)

    assert closed == ["session-b", "client-b", "session-a", "client-a"]
    assert not manager._sessions  # pylint: disable=protected-access


def test_apply_replaces_the_shipped_teardown_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Applying the patches installs the fix and a second call changes nothing."""
    ogx_mcp.MCPSessionManager.__aexit__ = patches.SHIPPED_MCP_SESSION_EXIT  # type: ignore[method-assign]

    with caplog.at_level("INFO"):
        patches.apply_ogx_library_patches()
        patches.apply_ogx_library_patches()

    assert (
        ogx_mcp.MCPSessionManager.__aexit__ is patches.close_mcp_sessions_newest_first
    )
    assert sum("newest first" in record.message for record in caplog.records) == 1


@pytest.mark.parametrize(
    "source",
    [
        "async def __aexit__(self, *exc):\n    await self.close_all()\n",
        (
            "async def __aexit__(self, *exc):\n"
            "    for key in reversed(list(self._sessions.items())):\n        pass\n"
        ),
    ],
    ids=["restructured", "already-fixed"],
)
def test_apply_leaves_a_changed_teardown_alone(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture, source: str
) -> None:
    """A teardown that no longer has the known shape is not touched."""
    ogx_mcp.MCPSessionManager.__aexit__ = patches.SHIPPED_MCP_SESSION_EXIT  # type: ignore[method-assign]
    mocker.patch.object(patches.inspect, "getsource", return_value=source)

    with caplog.at_level("WARNING"):
        patches.apply_ogx_library_patches()

    assert ogx_mcp.MCPSessionManager.__aexit__ is patches.SHIPPED_MCP_SESSION_EXIT
    assert any("LCORE-4782" in record.message for record in caplog.records)


@pytest.mark.parametrize(
    ("version", "patched"),
    [("1.2.5", True), ("1.0.0", True), ("1.2.6", False), ("2.0.0", False)],
)
def test_apply_without_source_goes_by_the_version(
    mocker: MockerFixture, version: str, patched: bool
) -> None:
    """Without source to inspect, only the versions known to be affected are patched."""
    ogx_mcp.MCPSessionManager.__aexit__ = patches.SHIPPED_MCP_SESSION_EXIT  # type: ignore[method-assign]
    mocker.patch.object(patches.inspect, "getsource", side_effect=OSError("no source"))
    mocker.patch.object(patches, "ogx_version", return_value=version)

    patches.apply_ogx_library_patches()

    is_patched = (
        ogx_mcp.MCPSessionManager.__aexit__ is patches.close_mcp_sessions_newest_first
    )
    assert is_patched == patched

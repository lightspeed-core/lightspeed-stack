"""Unit tests for agent history loading via the step store."""

from __future__ import annotations

from typing import Optional

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai_harness.step_persistence import (
    ContinuableSnapshot,
    InMemoryStepStore,
    RunRecord,
    continue_run,
)

from conversations.agent_history.history import (
    INCLUDE_INTERRUPTED,
    load_conversation_history,
    load_run_history,
)


def _messages(*, user: str = "one", assistant: str = "two") -> list:
    return [
        ModelRequest(parts=[UserPromptPart(content=user)]),
        ModelResponse(parts=[TextPart(content=assistant)]),
    ]


async def _seed_snapshot(
    store: InMemoryStepStore,
    *,
    run_id: str,
    conversation_id: str,
    messages: Optional[list] = None,
    state: str = "complete",
) -> None:
    await store.register_run(RunRecord(run_id=run_id, conversation_id=conversation_id))
    await store.save_snapshot(
        ContinuableSnapshot(
            run_id=run_id,
            step_index=0,
            messages=messages if messages is not None else _messages(),
            conversation_id=conversation_id,
            state=state,  # type: ignore[arg-type]
        )
    )


@pytest.mark.asyncio
async def test_load_run_history_uses_continue_run() -> None:
    """Continuing loads a snapshot through the harness continue API."""
    store = InMemoryStepStore()
    await _seed_snapshot(store, run_id="resp_a", conversation_id="c1")
    loaded = await load_run_history(store, "resp_a")
    direct = await continue_run(
        store, run_id="resp_a", include_interrupted=INCLUDE_INTERRUPTED
    )
    assert loaded == direct


@pytest.mark.asyncio
async def test_load_conversation_history_uses_latest_continuable_run() -> None:
    """Conversation history comes from the newest run with a continuable snapshot."""
    store = InMemoryStepStore()
    conv = "550e8400-e29b-41d4-a716-446655440000"
    await _seed_snapshot(
        store,
        run_id="resp_old",
        conversation_id=conv,
        messages=_messages(user="old-turn", assistant="old-reply"),
    )
    await _seed_snapshot(
        store,
        run_id="resp_new",
        conversation_id=conv,
        messages=_messages(user="new-turn", assistant="new-reply"),
    )
    loaded = await load_conversation_history(store, conv)
    expected = await continue_run(
        store, run_id="resp_new", include_interrupted=INCLUDE_INTERRUPTED
    )
    assert loaded == expected


@pytest.mark.asyncio
async def test_load_conversation_history_skips_snapshotless_latest_run() -> None:
    """A newer registered run without a snapshot does not hide older history."""
    store = InMemoryStepStore()
    conv = "conv-branch"
    await _seed_snapshot(store, run_id="resp_a", conversation_id=conv)
    await store.register_run(RunRecord(run_id="resp_b", conversation_id=conv))
    loaded = await load_conversation_history(store, conv)
    expected = await continue_run(
        store, run_id="resp_a", include_interrupted=INCLUDE_INTERRUPTED
    )
    assert loaded == expected


@pytest.mark.asyncio
async def test_load_run_history_missing_snapshot_returns_empty() -> None:
    """An explicit run with no continuable snapshot yields empty history."""
    store = InMemoryStepStore()
    await store.register_run(RunRecord(run_id="resp_bare", conversation_id="c1"))
    assert await load_run_history(store, "resp_bare") == []


@pytest.mark.asyncio
async def test_no_store_returns_empty_history() -> None:
    """When persistence is off, history loaders return empty lists."""
    assert await load_run_history(None, "resp_x") == []
    assert await load_conversation_history(None, "c1") == []

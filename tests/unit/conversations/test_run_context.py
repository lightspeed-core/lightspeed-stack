"""Unit tests for run context resolution (display + step store)."""

from __future__ import annotations

from typing import Optional

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai_harness.step_persistence import (
    ContinuableSnapshot,
    InMemoryStepStore,
    RunRecord,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from conversations.agent_history.ids import with_conversation_prefix
from conversations.agent_history.models import RunResolutionParams
from conversations.run_context import resolve_run_context
from tests.unit.conversations.display_history.persistence.sample_rows import (
    SAMPLE_TURN,
    TEST_CONVERSATION_ID,
    TEST_USER_ID,
    new_conversation,
    new_turn,
)


def _messages() -> list:
    return [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        ModelResponse(parts=[TextPart(content="there")]),
    ]


async def _seed_step_store(
    store: InMemoryStepStore, run_id: str, conversation_id: str
) -> None:
    await store.register_run(RunRecord(run_id=run_id, conversation_id=conversation_id))
    await store.save_snapshot(
        ContinuableSnapshot(
            run_id=run_id,
            step_index=0,
            messages=_messages(),
            conversation_id=conversation_id,
            state="complete",  # type: ignore[arg-type]
        )
    )


def _seed_display_tip(
    session: Session,
    *,
    last_response_id: Optional[str],
) -> None:
    conv = new_conversation()
    if last_response_id is not None:
        conv.last_response_id = last_response_id
    session.add(conv)
    session.add(new_turn())
    session.commit()


@pytest.mark.asyncio
async def test_resolve_run_context_stateless() -> None:
    """No ids and store false yields only a new response id."""
    resolved = await resolve_run_context(
        InMemoryStepStore(),
        RunResolutionParams(TEST_USER_ID, False, store=False),
    )
    assert resolved.run_id.startswith("resp_")
    assert resolved.conversation_id is None
    assert resolved.message_history == []


@pytest.mark.asyncio
async def test_resolve_run_context_new_stored_thread() -> None:
    """No ids and store true mints a new conversation."""
    resolved = await resolve_run_context(
        None,
        RunResolutionParams(TEST_USER_ID, False),
    )
    assert resolved.conversation_id is not None
    assert resolved.conversation_id.startswith("conv_")


@pytest.mark.asyncio
@pytest.mark.usefixtures("patch_display_history_session")
async def test_resolve_run_context_from_conversation(
    memory_engine: Engine,
) -> None:
    """Continuing by conversation id loads harness history."""
    with Session(memory_engine) as session:
        _seed_display_tip(session, last_response_id=None)
    store = InMemoryStepStore()
    await _seed_step_store(store, SAMPLE_TURN["response_id"], TEST_CONVERSATION_ID)

    resolved = await resolve_run_context(
        store,
        RunResolutionParams(
            TEST_USER_ID,
            False,
            conversation_id=with_conversation_prefix(TEST_CONVERSATION_ID),
        ),
    )
    assert resolved.conversation_id == with_conversation_prefix(TEST_CONVERSATION_ID)
    assert len(resolved.message_history) == 2


@pytest.mark.asyncio
@pytest.mark.usefixtures("patch_display_history_session")
async def test_resolve_run_context_from_previous_response_tip(
    memory_engine: Engine,
) -> None:
    """When the response is still the tip, keep the same conversation."""
    with Session(memory_engine) as session:
        _seed_display_tip(session, last_response_id=SAMPLE_TURN["response_id"])
    store = InMemoryStepStore()
    await _seed_step_store(store, SAMPLE_TURN["response_id"], TEST_CONVERSATION_ID)

    resolved = await resolve_run_context(
        store,
        RunResolutionParams(
            TEST_USER_ID,
            False,
            previous_response_id=SAMPLE_TURN["response_id"],
        ),
    )
    assert resolved.conversation_id == with_conversation_prefix(TEST_CONVERSATION_ID)
    assert len(resolved.message_history) == 2


@pytest.mark.asyncio
@pytest.mark.usefixtures("patch_display_history_session")
async def test_resolve_run_context_from_previous_response_fork(
    memory_engine: Engine,
) -> None:
    """When the response is not the tip, fork to a new conversation."""
    with Session(memory_engine) as session:
        _seed_display_tip(session, last_response_id="resp-newer")
    store = InMemoryStepStore()
    await _seed_step_store(store, SAMPLE_TURN["response_id"], TEST_CONVERSATION_ID)

    resolved = await resolve_run_context(
        store,
        RunResolutionParams(
            TEST_USER_ID,
            False,
            previous_response_id=SAMPLE_TURN["response_id"],
        ),
    )
    assert resolved.conversation_id is not None
    assert resolved.conversation_id != with_conversation_prefix(TEST_CONVERSATION_ID)
    assert len(resolved.message_history) == 2

"""Tests for storing projected agent turns in display history."""

import pytest
from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.run import AgentRunResult
from pydantic_ai.usage import RunUsage
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from conversations.display_history.persistence.facade.agentic_turn import (
    store_agentic_turn,
)
from conversations.display_history.persistence.repository.agentic_turn import (
    get_agentic_turn,
)
from models.common.agents import AgentRunDeps
from tests.unit.conversations.display_history.persistence.sample_rows import (
    TEST_CONVERSATION_ID,
    seed_sample_conversation_and_turn,
)


def _completed_run() -> AgentRunResult[str]:
    run = AgentRunResult(output="there")
    run._state.run_id = "resp_1"  # pylint: disable=protected-access
    run._state.usage = RunUsage(  # pylint: disable=protected-access
        input_tokens=4,
        output_tokens=6,
    )
    run._state.message_history = [  # pylint: disable=protected-access
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        ModelResponse(
            parts=[TextPart(content="there")],
            finish_reason="stop",  # type: ignore[arg-type]
        ),
    ]
    return run


def test_store_skips_run_without_id() -> None:
    """A run cancelled before start is not persisted."""
    run = RunCancelled("cancelled before start", run_id=None)
    assert store_agentic_turn("conv-1", 1, run, AgentRunDeps()) is None


@pytest.mark.usefixtures("patch_display_history_session")
def test_store_persists_projected_run(memory_engine: Engine) -> None:
    """A completed run is written onto the existing turn envelope."""
    with Session(memory_engine) as session:
        conversation_id, turn_number = seed_sample_conversation_and_turn(session)

    row = store_agentic_turn(
        conversation_id, turn_number, _completed_run(), AgentRunDeps()
    )
    assert row is not None
    assert row.status == "completed"
    assert row.input_tokens == 4
    assert row.output_tokens == 6

    loaded = get_agentic_turn(TEST_CONVERSATION_ID, turn_number)
    assert loaded is not None
    assert loaded.status == "completed"

"""Tests for projecting agent runs into turn summaries."""

from typing import Optional

import pytest
from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.run import AgentRunResult
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.usage import RunUsage

from conversations.display_history.agentic.models.turn_items import MessageTurnItem
from conversations.display_history.agentic.models.types import AgentTurnStatus
from conversations.display_history.agentic.projection import project_agent_turn_summary
from knowledge.types import KnowledgeMatch
from models.common.agents import AgentRunDeps
from models.common.turn_summary import ReferencedDocument


def _user_and_assistant(
    *,
    finish_reason: Optional[str] = "stop",
    provider_details: Optional[dict[str, str]] = None,
) -> list:
    return [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        ModelResponse(
            parts=[TextPart(content="there")],
            finish_reason=finish_reason,  # type: ignore[arg-type]
            provider_details=provider_details,
        ),
    ]


def _completed_run(
    *,
    run_id: str = "resp_1",
    input_tokens: int = 4,
    output_tokens: int = 6,
    messages: Optional[list] = None,
    output: object = "there",
) -> AgentRunResult[object]:
    run = AgentRunResult(output=output)  # type: ignore[arg-type]
    run._state.run_id = run_id  # pylint: disable=protected-access
    run._state.usage = RunUsage(  # pylint: disable=protected-access
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    run._state.message_history = (  # pylint: disable=protected-access
        messages if messages is not None else _user_and_assistant()
    )
    return run


def test_project_skips_run_without_id() -> None:
    """A run cancelled before start has no identity to persist."""
    run = RunCancelled("cancelled before start", run_id=None)
    assert project_agent_turn_summary(run, AgentRunDeps()) is None


def test_project_completed_run_to_summary() -> None:
    """Completed runs become persistence fields without envelope identity."""
    summary = project_agent_turn_summary(_completed_run(), AgentRunDeps())
    assert summary is not None
    assert summary.status == "completed"
    assert summary.input_tokens == 4
    assert summary.output_tokens == 6
    assert summary.context_status == "full"
    assert summary.agent is None
    assert isinstance(summary.input[0], MessageTurnItem)
    assert isinstance(summary.output[0], MessageTurnItem)


def test_project_cancelled_run_is_interrupted() -> None:
    """RunCancelled with a run id persists as interrupted."""
    run = RunCancelled(
        "cancelled",
        run_id="resp_cancel",
        messages=_user_and_assistant(),
        usage=RunUsage(input_tokens=1, output_tokens=2),
    )
    summary = project_agent_turn_summary(run, AgentRunDeps())
    assert summary is not None
    assert summary.status == "interrupted"
    assert summary.input_tokens == 1
    assert summary.output_tokens == 2


def test_project_applies_deps_and_run_citations() -> None:
    """Deps compaction and citations are merged with knowledge-search documents."""
    match = KnowledgeMatch(
        content="Kept.",
        score=1.0,
        source="https://docs.example/kept",
        metadata={"title": "Kept"},
    )
    messages = [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        ModelResponse(parts=[TextPart(content="there")], finish_reason="stop"),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="search_knowledge",
                    content=[match],
                    tool_call_id="call_k",
                )
            ]
        ),
    ]
    deps = AgentRunDeps(
        context_status="compacted",
        referenced_documents=[ReferencedDocument(doc_title="OpenShift Docs")],
    )
    summary = project_agent_turn_summary(_completed_run(messages=messages), deps)
    assert summary is not None
    assert summary.context_status == "compacted"
    assert summary.agent is None
    assert [doc.doc_title for doc in summary.referenced_documents] == [
        "OpenShift Docs",
        "Kept",
    ]


@pytest.mark.parametrize(
    ("finish_reason", "status"),
    [
        ("stop", "completed"),
        ("content_filter", "completed"),
        ("length", "failed"),
        ("error", "failed"),
        ("tool_call", "completed"),
        ("something_else", "completed"),
        (None, "completed"),
    ],
)
def test_project_maps_finish_reason(
    finish_reason: Optional[str], status: AgentTurnStatus
) -> None:
    """Finish reason maps onto stored turn status, defaulting to completed."""
    summary = project_agent_turn_summary(
        _completed_run(messages=_user_and_assistant(finish_reason=finish_reason)),
        AgentRunDeps(),
    )
    assert summary is not None
    assert summary.status == status


def test_project_deduplicates_citations_across_deps_and_knowledge() -> None:
    """The same document from inline RAG and search_knowledge appears once."""
    match = KnowledgeMatch(
        content="Kept.",
        score=1.0,
        source="https://docs.example/kept",
        metadata={"title": "Kept"},
    )
    messages = [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        ModelResponse(parts=[TextPart(content="there")], finish_reason="stop"),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="search_knowledge",
                    content=[match],
                    tool_call_id="call_k",
                )
            ]
        ),
    ]
    url = "https://docs.example/kept"
    deps = AgentRunDeps(
        referenced_documents=[ReferencedDocument(doc_title="Kept", doc_url=url)]
    )
    summary = project_agent_turn_summary(_completed_run(messages=messages), deps)
    assert summary is not None
    assert len(summary.referenced_documents) == 1
    assert summary.referenced_documents[0].doc_title == "Kept"
    assert str(summary.referenced_documents[0].doc_url) == url


def test_project_deferred_tool_output_is_awaiting_input() -> None:
    """Deferred client tools end the run with awaiting_input."""
    summary = project_agent_turn_summary(
        _completed_run(
            output=DeferredToolRequests(),
            messages=_user_and_assistant(finish_reason="tool_call"),
        ),
        AgentRunDeps(),
    )
    assert summary is not None
    assert summary.status == "awaiting_input"


def test_project_provider_cancelled_is_interrupted() -> None:
    """A cancelled provider finish is stored as interrupted."""
    summary = project_agent_turn_summary(
        _completed_run(
            messages=_user_and_assistant(
                provider_details={"finish_reason": "cancelled"}
            )
        ),
        AgentRunDeps(),
    )
    assert summary is not None
    assert summary.status == "interrupted"


def test_project_missing_response_is_failed() -> None:
    """A run with no model response is stored as failed."""
    summary = project_agent_turn_summary(
        _completed_run(messages=[ModelRequest(parts=[UserPromptPart(content="hi")])]),
        AgentRunDeps(),
    )
    assert summary is not None
    assert summary.status == "failed"

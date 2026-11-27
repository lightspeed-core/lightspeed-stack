"""Tests for the per-run capability collector."""

import pytest

from models.common.agents import AgentRunDeps, public_context_status
from models.common.turn_summary import ReferencedDocument


def test_run_deps_defaults() -> None:
    """A new collector is full context with no inline documents."""
    deps = AgentRunDeps()
    assert deps.context_status == "full"
    assert deps.referenced_documents == []


def test_run_deps_mutates_in_place() -> None:
    """Capabilities write fields on the same instance the caller holds."""
    deps = AgentRunDeps()
    deps.context_status = "compacted"
    deps.referenced_documents.append(ReferencedDocument(doc_title="Docs"))
    assert deps.context_status == "compacted"
    assert deps.referenced_documents[0].doc_title == "Docs"


@pytest.mark.parametrize(
    ("pre_agent", "run", "expected"),
    [
        ("full", "full", "full"),
        ("summarized", "full", "summarized"),
        ("full", "compacted", "summarized"),
        ("summarized", "compacted", "summarized"),
    ],
)
def test_public_context_status_combines_both_paths(
    pre_agent: str, run: str, expected: str
) -> None:
    """Either compaction path having acted makes the public field summarized."""
    assert public_context_status(pre_agent, run) == expected  # type: ignore[arg-type]

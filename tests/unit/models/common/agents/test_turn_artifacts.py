"""Tests for the per-run PAI artifacts."""

from pytest_mock import MockerFixture

from models.common.agents import AgentRunDeps, AgentTurnArtifacts


def test_unrecorded_artifacts_report_a_full_context() -> None:
    """A run that never happened or failed left nothing to report."""
    assert AgentTurnArtifacts().run_context_status() == "full"


def test_recorded_artifacts_report_the_runs_status(mocker: MockerFixture) -> None:
    """The deps the compaction capability marked are what the endpoints read."""
    artifacts = AgentTurnArtifacts()
    artifacts.record(mocker.Mock(), AgentRunDeps(context_status="compacted"))
    assert artifacts.run_context_status() == "compacted"

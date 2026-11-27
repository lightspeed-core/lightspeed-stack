"""Unit tests for step persistence settings built from a query."""

from agent.types.settings.step_persistence import StepPersistenceSettings
from models.api.requests import QueryRequest


def test_query_does_not_select_step_persistence() -> None:
    """Every query keeps step persistence enabled.

    The history service decides whether a store exists. The query is accepted
    so every setting is built the same way.
    """
    request = QueryRequest(query="What is Kubernetes?")

    assert StepPersistenceSettings.from_query_request(
        request
    ) == StepPersistenceSettings(enabled=True)

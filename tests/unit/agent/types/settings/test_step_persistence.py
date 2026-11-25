"""Unit tests for step persistence settings built from a query or Responses request."""

from agent.types.settings.step_persistence import StepPersistenceSettings
from models.api.requests import QueryRequest, ResponsesRequest


def test_query_does_not_select_step_persistence() -> None:
    """Every query keeps step persistence enabled.

    The history service decides whether a store exists. The query is accepted
    so every setting is built the same way.
    """
    request = QueryRequest(query="What is Kubernetes?")

    assert StepPersistenceSettings.from_query_request(
        request
    ) == StepPersistenceSettings(enabled=True)


def test_responses_store_flag_enables_step_persistence() -> None:
    """A Responses request with store enabled keeps step persistence on."""
    request = ResponsesRequest(input="What is Kubernetes?", store=True)

    assert StepPersistenceSettings.from_responses_request(
        request
    ) == StepPersistenceSettings(enabled=True)


def test_responses_store_flag_disables_step_persistence() -> None:
    """A Responses request with store disabled turns step persistence off."""
    request = ResponsesRequest(input="What is Kubernetes?", store=False)

    assert StepPersistenceSettings.from_responses_request(
        request
    ) == StepPersistenceSettings(enabled=False)


def test_omitted_responses_store_flag_enables_step_persistence() -> None:
    """An omitted store flag defaults to enabled step persistence."""
    request = ResponsesRequest(input="What is Kubernetes?")

    assert request.store is True
    assert StepPersistenceSettings.from_responses_request(
        request
    ) == StepPersistenceSettings(enabled=True)

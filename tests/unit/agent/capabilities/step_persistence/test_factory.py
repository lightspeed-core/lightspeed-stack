"""Unit tests for step persistence capability construction."""

from pytest_mock import MockerFixture

from agent.capabilities.step_persistence.factory import StepPersistenceFactory


def test_returns_the_agent_history_capability(mocker: MockerFixture) -> None:
    """The factory returns the capability owned by the agent history service."""
    capability = mocker.Mock()
    service = mocker.Mock(step_persistence=capability)
    mocker.patch(
        "agent.capabilities.step_persistence.factory.AgentHistoryService",
        return_value=service,
    )

    assert StepPersistenceFactory.build_capability() is capability


def test_returns_none_when_persistence_is_disabled(mocker: MockerFixture) -> None:
    """A history service without a store produces no capability."""
    service = mocker.Mock(step_persistence=None)
    mocker.patch(
        "agent.capabilities.step_persistence.factory.AgentHistoryService",
        return_value=service,
    )

    assert StepPersistenceFactory.build_capability() is None

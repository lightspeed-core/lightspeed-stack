"""Unit tests for step persistence capability construction."""

from pytest_mock import MockerFixture

from agent.capabilities.step_persistence.factory import StepPersistenceFactory
from agent.types.settings import StepPersistenceSettings


def test_returns_the_agent_history_capability(mocker: MockerFixture) -> None:
    """Enabled settings return the capability owned by the history service."""
    capability = mocker.Mock()
    service = mocker.Mock(step_persistence=capability)
    history = mocker.patch(
        "agent.capabilities.step_persistence.factory.AgentHistoryService",
        return_value=service,
    )

    assert (
        StepPersistenceFactory.build_capability(StepPersistenceSettings(enabled=True))
        is capability
    )
    history.assert_called_once_with()


def test_returns_none_when_no_store_is_configured(mocker: MockerFixture) -> None:
    """Enabled settings still produce no capability when the store is a no-op."""
    service = mocker.Mock(step_persistence=None)
    mocker.patch(
        "agent.capabilities.step_persistence.factory.AgentHistoryService",
        return_value=service,
    )

    assert (
        StepPersistenceFactory.build_capability(StepPersistenceSettings(enabled=True))
        is None
    )


def test_disabled_settings_build_nothing(mocker: MockerFixture) -> None:
    """Disabled settings do not ask the history service for a capability."""
    history = mocker.patch(
        "agent.capabilities.step_persistence.factory.AgentHistoryService",
    )

    assert (
        StepPersistenceFactory.build_capability(StepPersistenceSettings(enabled=False))
        is None
    )

    history.assert_not_called()

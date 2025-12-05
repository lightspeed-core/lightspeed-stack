"""Shared pytest fixtures for unit tests."""

from __future__ import annotations

from typing import Generator

import pytest
from pytest_mock import AsyncMockType, MockerFixture

from configuration import AppConfig

type AgentFixtures = Generator[
    tuple[
        AsyncMockType,
        AsyncMockType,
    ],
    None,
    None,
]


@pytest.fixture(name="prepare_agent_mocks", scope="function")
def prepare_agent_mocks_fixture(
    mocker: MockerFixture,
) -> AgentFixtures:
    """Prepare for mock for the LLM agent.

    Provides common mocks for AsyncLlamaStackClient and AsyncAgent
    with proper agent_id setup to avoid initialization errors.

    Yields:
        tuple: (mock_client, mock_agent)
    """
    mock_client = mocker.AsyncMock()
    mock_agent = mocker.AsyncMock()

    # Set up agent_id property to avoid "Agent ID not initialized" error
    mock_agent._agent_id = "test_agent_id"  # pylint: disable=protected-access
    mock_agent.agent_id = "test_agent_id"

    # Set up create_turn mock structure for query endpoints that need it
    mock_agent.create_turn.return_value.steps = []

    yield mock_client, mock_agent


@pytest.fixture(name="minimal_config")
def minimal_config_fixture() -> AppConfig:
    """Create a minimal AppConfig with only required fields.

    This fixture provides a minimal valid configuration that can be used
    in tests that don't need specific configuration values. It includes
    only the required fields to avoid unnecessary instantiation.

    Returns:
        AppConfig: A minimal AppConfig instance with required fields only.
    """
    cfg = AppConfig()
    cfg.init_from_dict(
        {
            "name": "test",
            "service": {"host": "localhost", "port": 8080},
            "llama_stack": {
                "api_key": "test-key",
                "url": "http://test.com:1234",
                "use_as_library_client": False,
            },
            "user_data_collection": {},
            "authentication": {"module": "noop"},
            "authorization": {"access_rules": []},
        }
    )
    return cfg

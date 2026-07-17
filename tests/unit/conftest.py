"""Shared pytest fixtures for unit tests."""

from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
from llama_stack_client import AsyncLlamaStackClient
from pytest_mock import AsyncMockType, MockerFixture

from lightspeed_stack.configuration import AppConfig
from lightspeed_stack.constants import DEFAULT_LOGGER_NAME
from lightspeed_stack.models.common.responses.responses_api_params import ResponsesApiParams
from lightspeed_stack.models.config import SkillsConfiguration

type AgentFixtures = Generator[
    tuple[
        AsyncMockType,
        AsyncMockType,
    ],
    None,
    None,
]


@pytest.fixture(autouse=True)
def reset_logging_state() -> Generator[None, None, None]:
    """Reset logging state before and after each test.

    Module-level calls to setup_logging() (such as from importing lightspeed_stack)
    set propagate=False on the application logger, which prevents caplog from
    capturing log records.

    This fixture ensures propagation is enabled during tests and restores the
    original logger state afterward. It also clears the setup_logging lru_cache
    so tests that call setup_logging() get a fresh configuration.
    """
    logger = logging.getLogger(DEFAULT_LOGGER_NAME)
    original_propagate = logger.propagate
    original_handlers = logger.handlers[:]
    original_level = logger.level
    logger.propagate = True

    yield

    logger.propagate = original_propagate
    logger.handlers = original_handlers
    logger.level = original_level


@pytest.fixture(name="prepare_agent_mocks", scope="function")
def prepare_agent_mocks_fixture(
    mocker: MockerFixture,
) -> AgentFixtures:
    """Prepare for mock for the LLM agent.

    Provides common mocks for AsyncLlamaStackClient and AsyncAgent
    with proper agent_id setup to avoid initialization errors.

    Yields:
        tuple: (mock_client, mock_agent) — two AsyncMock objects
        representing the client and the agent.
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


@pytest.fixture(name="mock_client")
def mock_client_fixture(  # pylint: disable=protected-access
    mocker: MockerFixture,
) -> AsyncLlamaStackClient:
    """Remote Llama Stack client mock for build_agent tests."""
    client = mocker.Mock(spec=AsyncLlamaStackClient)
    client.base_url = "http://localhost:8321"
    client.api_key = "test-key"
    client._client = mocker.Mock(spec=httpx.AsyncClient)
    client.default_headers = {}
    return client


@pytest.fixture(name="mock_params")
def mock_params_fixture() -> ResponsesApiParams:
    """Minimal ResponsesApiParams for build_agent and similar utils tests."""
    return ResponsesApiParams(
        model="provider/my-model",
        input="test",
        conversation="conv-test",
        instructions="Be helpful.",
        store=False,
        stream=False,
    )


@pytest.fixture(name="mock_skills_configuration")
def mock_skills_configuration_fixture(tmp_path: Path) -> SkillsConfiguration:
    """Filesystem-backed SkillsConfiguration with a single test skill."""
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: Test skill.\n---\n\nDo the thing.\n",
        encoding="utf-8",
    )
    return SkillsConfiguration(paths=[skills_root])

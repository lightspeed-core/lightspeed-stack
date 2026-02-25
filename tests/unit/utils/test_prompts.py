"""Unit tests for prompts utility functions."""

import pytest
from fastapi import HTTPException
from pytest_mock import MockerFixture

import constants
from configuration import AppConfig
from models.config import CustomProfile
from models.requests import QueryRequest
from tests.unit import config_dict
from utils import prompts

CONFIGURED_SYSTEM_PROMPT = "This is a configured system prompt"


@pytest.fixture(name="config_without_system_prompt")
def config_without_system_prompt_fixture() -> AppConfig:
    """Configuration w/o custom system prompt set."""
    test_config = config_dict.copy()

    # no customization provided
    test_config["customization"] = None

    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    return cfg


@pytest.fixture(name="config_with_custom_system_prompt")
def config_with_custom_system_prompt_fixture() -> AppConfig:
    """Configuration with custom system prompt set."""
    test_config = config_dict.copy()

    # system prompt is customized
    test_config["customization"] = {
        "system_prompt": CONFIGURED_SYSTEM_PROMPT,
    }
    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    return cfg


@pytest.fixture(name="config_with_custom_system_prompt_and_disable_query_system_prompt")
def config_with_custom_system_prompt_and_disable_query_system_prompt_fixture() -> (
    AppConfig
):
    """Configuration with custom system prompt and disabled query system prompt set."""
    test_config = config_dict.copy()

    # system prompt is customized and query system prompt is disabled
    test_config["customization"] = {
        "system_prompt": CONFIGURED_SYSTEM_PROMPT,
        "disable_query_system_prompt": True,
    }
    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    return cfg


@pytest.fixture(
    name="config_with_custom_profile_prompt_and_enabled_query_system_prompt"
)
def config_with_custom_profile_prompt_and_enabled_query_system_prompt_fixture() -> (
    AppConfig
):
    """Configuration with custom profile loaded for prompt and disabled query system prompt set."""
    test_config = config_dict.copy()

    test_config["customization"] = {
        "profile_path": "tests/profiles/test/profile.py",
        "system_prompt": CONFIGURED_SYSTEM_PROMPT,
        "disable_query_system_prompt": False,
    }
    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    return cfg


@pytest.fixture(
    name="config_with_custom_profile_prompt_and_disable_query_system_prompt"
)
def config_with_custom_profile_prompt_and_disable_query_system_prompt_fixture() -> (
    AppConfig
):
    """Configuration with custom profile loaded for prompt and disabled query system prompt set."""
    test_config = config_dict.copy()

    test_config["customization"] = {
        "profile_path": "tests/profiles/test/profile.py",
        "system_prompt": CONFIGURED_SYSTEM_PROMPT,
        "disable_query_system_prompt": True,
    }
    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    return cfg


@pytest.fixture(name="query_request_without_system_prompt")
def query_request_without_system_prompt_fixture() -> QueryRequest:
    """Fixture for query request without system prompt."""
    return QueryRequest(
        query="query", system_prompt=None
    )  # pyright: ignore[reportCallIssue]


@pytest.fixture(name="query_request_with_system_prompt")
def query_request_with_system_prompt_fixture() -> QueryRequest:
    """Fixture for query request with system prompt."""
    return QueryRequest(
        query="query", system_prompt="System prompt defined in query"
    )  # pyright: ignore[reportCallIssue]


@pytest.fixture(name="setup_configuration")
def setup_configuration_fixture() -> AppConfig:
    """Set up configuration for tests."""
    test_config_dict = {
        "name": "test",
        "service": {
            "host": "localhost",
            "port": 8080,
            "auth_enabled": False,
            "workers": 1,
            "color_log": True,
            "access_log": True,
        },
        "llama_stack": {
            "api_key": "test-key",
            "url": "http://test.com:1234",
            "use_as_library_client": False,
        },
        "user_data_collection": {
            "transcripts_enabled": False,
        },
        "mcp_servers": [],
    }
    cfg = AppConfig()
    cfg.init_from_dict(test_config_dict)
    return cfg


def test_get_default_system_prompt(
    config_without_system_prompt: AppConfig,
    query_request_without_system_prompt: QueryRequest,
    mocker: MockerFixture,
) -> None:
    """Test that default system prompt is returned when other prompts are not provided."""
    mocker.patch("utils.prompts.configuration", config_without_system_prompt)
    system_prompt = prompts.get_system_prompt(
        query_request_without_system_prompt.system_prompt
    )
    assert system_prompt == constants.DEFAULT_SYSTEM_PROMPT


def test_get_customized_system_prompt(
    config_with_custom_system_prompt: AppConfig,
    query_request_without_system_prompt: QueryRequest,
    mocker: MockerFixture,
) -> None:
    """Test that customized system prompt is used when system prompt is not provided in query."""
    mocker.patch("utils.prompts.configuration", config_with_custom_system_prompt)
    system_prompt = prompts.get_system_prompt(
        query_request_without_system_prompt.system_prompt
    )
    assert system_prompt == CONFIGURED_SYSTEM_PROMPT


def test_get_query_system_prompt(
    config_without_system_prompt: AppConfig,
    query_request_with_system_prompt: QueryRequest,
    mocker: MockerFixture,
) -> None:
    """Test that system prompt from query is returned."""
    mocker.patch("utils.prompts.configuration", config_without_system_prompt)
    system_prompt = prompts.get_system_prompt(
        query_request_with_system_prompt.system_prompt
    )
    assert system_prompt == query_request_with_system_prompt.system_prompt


def test_get_query_system_prompt_not_customized_one(
    config_with_custom_system_prompt: AppConfig,
    query_request_with_system_prompt: QueryRequest,
    mocker: MockerFixture,
) -> None:
    """Test that system prompt from query is returned even when customized one is specified."""
    mocker.patch("utils.prompts.configuration", config_with_custom_system_prompt)
    system_prompt = prompts.get_system_prompt(
        query_request_with_system_prompt.system_prompt
    )
    assert system_prompt == query_request_with_system_prompt.system_prompt


def test_get_system_prompt_with_disable_query_system_prompt(
    config_with_custom_system_prompt_and_disable_query_system_prompt: AppConfig,
    query_request_with_system_prompt: QueryRequest,
    mocker: MockerFixture,
) -> None:
    """Test that query system prompt is disallowed when disable_query_system_prompt is True."""
    mocker.patch(
        "utils.prompts.configuration",
        config_with_custom_system_prompt_and_disable_query_system_prompt,
    )
    with pytest.raises(HTTPException) as exc_info:
        prompts.get_system_prompt(query_request_with_system_prompt.system_prompt)
    assert exc_info.value.status_code == 422


def test_get_system_prompt_with_disable_query_system_prompt_and_non_system_prompt_query(
    config_with_custom_system_prompt_and_disable_query_system_prompt: AppConfig,
    query_request_without_system_prompt: QueryRequest,
    mocker: MockerFixture,
) -> None:
    """Test that query without system prompt is allowed when disable_query_system_prompt is True."""
    mocker.patch(
        "utils.prompts.configuration",
        config_with_custom_system_prompt_and_disable_query_system_prompt,
    )
    system_prompt = prompts.get_system_prompt(
        query_request_without_system_prompt.system_prompt
    )
    assert system_prompt == CONFIGURED_SYSTEM_PROMPT


def test_get_profile_prompt_with_disable_query_system_prompt(
    config_with_custom_profile_prompt_and_disable_query_system_prompt: AppConfig,
    query_request_without_system_prompt: QueryRequest,
    mocker: MockerFixture,
) -> None:
    """Test that system prompt is set if profile enabled and query system prompt disabled."""
    mocker.patch(
        "utils.prompts.configuration",
        config_with_custom_profile_prompt_and_disable_query_system_prompt,
    )
    custom_profile = CustomProfile(path="tests/profiles/test/profile.py")
    profile_prompts = custom_profile.get_prompts()
    system_prompt = prompts.get_system_prompt(
        query_request_without_system_prompt.system_prompt
    )
    assert system_prompt == profile_prompts.get("default")


def test_get_profile_prompt_with_enabled_query_system_prompt(
    config_with_custom_profile_prompt_and_enabled_query_system_prompt: AppConfig,
    query_request_with_system_prompt: QueryRequest,
    mocker: MockerFixture,
) -> None:
    """Test that profile system prompt is overridden by query system prompt enabled."""
    mocker.patch(
        "utils.prompts.configuration",
        config_with_custom_profile_prompt_and_enabled_query_system_prompt,
    )
    system_prompt = prompts.get_system_prompt(
        query_request_with_system_prompt.system_prompt
    )
    assert system_prompt == query_request_with_system_prompt.system_prompt


def test_get_topic_summary_system_prompt_default(
    setup_configuration: AppConfig,
    mocker: MockerFixture,
) -> None:
    """Test that default topic summary system prompt is returned when no custom
    profile is configured.
    """
    mocker.patch("utils.prompts.configuration", setup_configuration)
    topic_summary_prompt = prompts.get_topic_summary_system_prompt()
    assert topic_summary_prompt == constants.DEFAULT_TOPIC_SUMMARY_SYSTEM_PROMPT


def test_get_topic_summary_system_prompt_with_custom_profile(
    mocker: MockerFixture,
) -> None:
    """Test that custom profile topic summary prompt is returned when available."""
    test_config = config_dict.copy()
    test_config["customization"] = {
        "profile_path": "tests/profiles/test/profile.py",
    }
    cfg = AppConfig()
    cfg.init_from_dict(test_config)
    mocker.patch("utils.prompts.configuration", cfg)

    # Mock the custom profile to return a topic_summary prompt
    custom_profile = CustomProfile(path="tests/profiles/test/profile.py")
    profile_prompts = custom_profile.get_prompts()

    topic_summary_prompt = prompts.get_topic_summary_system_prompt()
    assert topic_summary_prompt == profile_prompts.get("topic_summary")


def test_get_topic_summary_system_prompt_with_custom_profile_no_topic_summary(
    mocker: MockerFixture,
) -> None:
    """Test that default topic summary prompt is returned when custom profile has
    no topic_summary prompt.
    """
    test_config = config_dict.copy()
    test_config["customization"] = {
        "profile_path": "tests/profiles/test/profile.py",
    }
    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    # Mock the custom profile to return None for topic_summary prompt
    mock_profile = mocker.Mock()
    mock_profile.get_prompts.return_value = {
        "default": "some prompt"
    }  # No topic_summary key

    # Patch the custom_profile property to return our mock
    mocker.patch.object(cfg.customization, "custom_profile", mock_profile)
    mocker.patch("utils.prompts.configuration", cfg)

    topic_summary_prompt = prompts.get_topic_summary_system_prompt()
    assert topic_summary_prompt == constants.DEFAULT_TOPIC_SUMMARY_SYSTEM_PROMPT


def test_get_topic_summary_system_prompt_no_customization(
    mocker: MockerFixture,
) -> None:
    """Test that default topic summary prompt is returned when customization is None."""
    test_config = config_dict.copy()
    test_config["customization"] = None
    cfg = AppConfig()
    cfg.init_from_dict(test_config)
    mocker.patch("utils.prompts.configuration", cfg)

    topic_summary_prompt = prompts.get_topic_summary_system_prompt()
    assert topic_summary_prompt == constants.DEFAULT_TOPIC_SUMMARY_SYSTEM_PROMPT

"""Unit tests for endpoints utility functions."""

import os
import pytest
from fastapi import HTTPException

import constants
from configuration import AppConfig
from tests.unit import config_dict

from models.requests import QueryRequest
from utils import endpoints

CONFIGURED_SYSTEM_PROMPT = "This is a configured system prompt"


@pytest.fixture(name="input_file")
def input_file_fixture(tmp_path):
    """Create file manually using the tmp_path fixture."""
    filename = os.path.join(tmp_path, "prompt.txt")
    with open(filename, "wt", encoding="utf-8") as fout:
        fout.write("this is prompt!")
    return filename


@pytest.fixture(name="config_without_system_prompt")
def config_without_system_prompt_fixture():
    """Configuration w/o custom system prompt set."""
    test_config = config_dict.copy()

    # no customization provided
    test_config["customization"] = None

    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    return cfg


@pytest.fixture(name="config_with_custom_system_prompt")
def config_with_custom_system_prompt_fixture():
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
def config_with_custom_system_prompt_and_disable_query_system_prompt_fixture():
    """Configuration with custom system prompt and disabled query systme prompt set."""
    test_config = config_dict.copy()

    # system prompt is customized and query system prompt is disabled
    test_config["customization"] = {
        "system_prompt": CONFIGURED_SYSTEM_PROMPT,
        "disable_query_system_prompt": True,
    }
    cfg = AppConfig()
    cfg.init_from_dict(test_config)

    return cfg


@pytest.fixture(name="query_request_without_system_prompt")
def query_request_without_system_prompt_fixture():
    """Fixture for query request without system prompt."""
    return QueryRequest(query="query", system_prompt=None)


@pytest.fixture(name="query_request_with_system_prompt")
def query_request_with_system_prompt_fixture():
    """Fixture for query request with system prompt."""
    return QueryRequest(query="query", system_prompt="System prompt defined in query")


def test_get_default_system_prompt(
    config_without_system_prompt, query_request_without_system_prompt
):
    """Test that default system prompt is returned when other prompts are not provided."""
    system_prompt = endpoints.get_system_prompt(
        query_request_without_system_prompt, config_without_system_prompt
    )
    assert system_prompt == constants.DEFAULT_SYSTEM_PROMPT


def test_get_customized_system_prompt(
    config_with_custom_system_prompt, query_request_without_system_prompt
):
    """Test that customized system prompt is used when system prompt is not provided in query."""
    system_prompt = endpoints.get_system_prompt(
        query_request_without_system_prompt, config_with_custom_system_prompt
    )
    assert system_prompt == CONFIGURED_SYSTEM_PROMPT


def test_get_query_system_prompt(
    config_without_system_prompt, query_request_with_system_prompt
):
    """Test that system prompt from query is returned."""
    system_prompt = endpoints.get_system_prompt(
        query_request_with_system_prompt, config_without_system_prompt
    )
    assert system_prompt == query_request_with_system_prompt.system_prompt


def test_get_query_system_prompt_not_customized_one(
    config_with_custom_system_prompt, query_request_with_system_prompt
):
    """Test that system prompt from query is returned even when customized one is specified."""
    system_prompt = endpoints.get_system_prompt(
        query_request_with_system_prompt, config_with_custom_system_prompt
    )
    assert system_prompt == query_request_with_system_prompt.system_prompt


def test_get_system_prompt_with_disable_query_system_prompt(
    config_with_custom_system_prompt_and_disable_query_system_prompt,
    query_request_with_system_prompt,
):
    """Test that query system prompt is disallowed when disable_query_system_prompt is True."""
    with pytest.raises(HTTPException) as exc_info:
        endpoints.get_system_prompt(
            query_request_with_system_prompt,
            config_with_custom_system_prompt_and_disable_query_system_prompt,
        )
    assert exc_info.value.status_code == 422


def test_get_system_prompt_with_disable_query_system_prompt_and_non_system_prompt_query(
    config_with_custom_system_prompt_and_disable_query_system_prompt,
    query_request_without_system_prompt,
):
    """Test that query without system prompt is allowed when disable_query_system_prompt is True."""
    system_prompt = endpoints.get_system_prompt(
        query_request_without_system_prompt,
        config_with_custom_system_prompt_and_disable_query_system_prompt,
    )
    assert system_prompt == CONFIGURED_SYSTEM_PROMPT

"""Unit tests for functions defined in utils.transcripts module."""

import json

from configuration import AppConfig
from models.requests import QueryRequest

from utils.transcripts import (
    construct_transcripts_path,
    store_transcript,
)
from utils.types import ToolCallSummary, TurnSummary


def test_construct_transcripts_path(mocker):
    """Test the construct_transcripts_path function."""

    config_dict = {
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
            "transcripts_storage": "/tmp/transcripts",
        },
    }
    cfg = AppConfig()
    cfg.init_from_dict(config_dict)
    # Update configuration for this test
    mocker.patch("utils.transcripts.configuration", cfg)

    user_id = "user123"

    path = construct_transcripts_path(user_id)

    assert (
        str(path) == "/tmp/transcripts/user123"
    ), "Path should be constructed correctly"


def test_store_transcript(mocker):
    """Test the store_transcript function."""

    # Mock file operations for new behavior
    mock_file = mocker.mock_open(read_data="")
    mocker.patch("builtins.open", mock_file)
    mocker.patch(
        "utils.transcripts.construct_transcripts_path",
        return_value=mocker.MagicMock(),
    )

    # Mock fcntl for file locking
    mock_fcntl = mocker.patch("utils.transcripts.fcntl")

    # Mock the JSON to assert the data is stored correctly
    mock_json = mocker.patch("utils.transcripts.json")
    mock_json.load.side_effect = json.JSONDecodeError("No JSON object", "", 0)

    # Mock parameters
    test_data = {
        "user_id": "user123",
        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
        "query": "What is OpenStack?",
        "model": "fake-model",
        "provider": "fake-provider",
        "query_is_valid": True,
        "rag_chunks": [],
        "truncated": False,
        "attachments": [],
    }

    query_request = QueryRequest(
        query=test_data["query"],
        model=test_data["model"],
        provider=test_data["provider"],
        conversation_id=test_data["conversation_id"],
        system_prompt=None,
        attachments=None,
        no_tools=False,
        media_type=None,
    )
    summary = TurnSummary(
        llm_response="LLM answer",
        tool_calls=[
            ToolCallSummary(
                id="123",
                name="test-tool",
                args="testing",
                response="tool response",
            )
        ],
    )

    store_transcript(
        test_data["user_id"],
        test_data["conversation_id"],
        test_data["model"],
        test_data["provider"],
        test_data["query_is_valid"],
        test_data["query"],
        query_request,
        summary,
        test_data["rag_chunks"],
        test_data["truncated"],
        test_data["attachments"],
    )

    # Assert file locking was used
    mock_fcntl.flock.assert_any_call(mocker.ANY, mock_fcntl.LOCK_EX)
    mock_fcntl.flock.assert_any_call(mocker.ANY, mock_fcntl.LOCK_UN)

    # Assert that the transcript was stored correctly with new structure
    expected_data = {
        "conversation_metadata": {
            "conversation_id": test_data["conversation_id"],
            "user_id": test_data["user_id"],
            "created_at": mocker.ANY,
            "last_updated": mocker.ANY,
        },
        "turns": [
            {
                "metadata": {
                    "provider": test_data["provider"],
                    "model": test_data["model"],
                    "query_provider": query_request.provider,
                    "query_model": query_request.model,
                    "timestamp": mocker.ANY,
                },
                "redacted_query": test_data["query"],
                "query_is_valid": test_data["query_is_valid"],
                "llm_response": summary.llm_response,
                "rag_chunks": test_data["rag_chunks"],
                "truncated": test_data["truncated"],
                "attachments": test_data["attachments"],
                "tool_calls": [
                    {
                        "id": "123",
                        "name": "test-tool",
                        "args": "testing",
                        "response": "tool response",
                    }
                ],
            }
        ],
    }

    mock_json.dump.assert_called_once_with(expected_data, mocker.ANY, indent=2)

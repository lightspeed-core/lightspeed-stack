"""Unit tests for functions defined in utils.transcripts module."""

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
    conversation_id = "123e4567-e89b-12d3-a456-426614174000"

    path = construct_transcripts_path(user_id, conversation_id)

    assert (
        str(path) == "/tmp/transcripts/user123/123e4567-e89b-12d3-a456-426614174000"
    ), "Path should be constructed correctly"


def test_store_transcript(mocker):
    """Test the store_transcript function."""

    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch(
        "utils.transcripts.construct_transcripts_path",
        return_value=mocker.MagicMock(),
    )

    # Mock the JSON to assert the data is stored correctly
    mock_json = mocker.patch("utils.transcripts.json")

    # Mock parameters
    user_id = "user123"
    conversation_id = "123e4567-e89b-12d3-a456-426614174000"
    query = "What is OpenStack?"
    model = "fake-model"
    provider = "fake-provider"
    query_request = QueryRequest(query=query, model=model, provider=provider)
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
    query_is_valid = True
    rag_chunks = []
    truncated = False
    attachments = []

    store_transcript(
        user_id,
        conversation_id,
        model,
        provider,
        query_is_valid,
        query,
        query_request,
        summary,
        rag_chunks,
        truncated,
        attachments,
    )

    # Assert that the transcript was stored correctly
    mock_json.dump.assert_called_once_with(
        {
            "metadata": {
                "provider": "fake-provider",
                "model": "fake-model",
                "query_provider": query_request.provider,
                "query_model": query_request.model,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "timestamp": mocker.ANY,
            },
            "redacted_query": query,
            "query_is_valid": query_is_valid,
            "llm_response": summary.llm_response,
            "rag_chunks": rag_chunks,
            "truncated": truncated,
            "attachments": attachments,
            "tool_calls": [
                {
                    "id": "123",
                    "name": "test-tool",
                    "args": "testing",
                    "response": "tool response",
                }
            ],
        },
        mocker.ANY,
    )

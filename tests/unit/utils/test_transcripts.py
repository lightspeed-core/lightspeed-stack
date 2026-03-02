"""Unit tests for functions defined in utils.transcripts module."""

import hashlib
from pytest_mock import MockerFixture

from configuration import AppConfig
from models.requests import QueryRequest

from utils.transcripts import (
    construct_transcripts_path,
    create_transcript,
    create_transcript_metadata,
    store_transcript,
)
from utils.types import ToolCallSummary, ToolResultSummary, TurnSummary


def test_construct_transcripts_path(mocker: MockerFixture) -> None:
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
    hashed_user_id = hashlib.sha256(user_id.encode("utf-8")).hexdigest()

    path = construct_transcripts_path(hashed_user_id, conversation_id)

    assert (
        str(path)
        == f"/tmp/transcripts/{hashed_user_id}/123e4567-e89b-12d3-a456-426614174000"
    ), "Path should be constructed correctly"


def test_store_transcript(  # pylint: disable=too-many-locals
    mocker: MockerFixture,
) -> None:
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
    query_request = QueryRequest(  # type: ignore[call-arg]
        query=query, model=model, provider=provider
    )
    summary = TurnSummary(
        llm_response="LLM answer",
        tool_calls=[
            ToolCallSummary(
                id="123",
                name="test-tool",
                args={"testing": "testing"},
                type="tool_call",
            )
        ],
        tool_results=[
            ToolResultSummary(
                id="123",
                status="success",
                content="tool response",
                type="tool_result",
                round=1,
            )
        ],
        rag_chunks=[],
    )
    query_is_valid = True
    truncated = False

    metadata = create_transcript_metadata(
        user_id=user_id,
        conversation_id=conversation_id,
        model_id=model,
        provider_id=provider,
        query_provider=query_request.provider,
        query_model=query_request.model,
    )
    transcript = create_transcript(
        metadata=metadata,
        redacted_query=query_request.query,
        summary=summary,
        attachments=query_request.attachments or [],
    )

    store_transcript(transcript)

    # Assert that the transcript was stored correctly
    hashed_user_id = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    mock_json.dump.assert_called_once()
    call_args = mock_json.dump.call_args[0]
    stored_data = call_args[0]

    assert stored_data["metadata"]["provider"] == "fake-provider"
    assert stored_data["metadata"]["model"] == "fake-model"
    assert stored_data["metadata"]["query_provider"] == query_request.provider
    assert stored_data["metadata"]["query_model"] == query_request.model
    assert stored_data["metadata"]["user_id"] == hashed_user_id
    assert stored_data["metadata"]["conversation_id"] == conversation_id
    assert "timestamp" in stored_data["metadata"]
    assert stored_data["redacted_query"] == query
    assert stored_data["query_is_valid"] == query_is_valid
    assert stored_data["llm_response"] == summary.llm_response
    assert stored_data["rag_chunks"] == []
    assert stored_data["truncated"] == truncated
    assert stored_data["attachments"] == []
    assert len(stored_data["tool_calls"]) == 1
    assert stored_data["tool_calls"][0]["id"] == "123"
    assert stored_data["tool_calls"][0]["name"] == "test-tool"
    assert len(stored_data["tool_results"]) == 1
    assert stored_data["tool_results"][0]["id"] == "123"

"""Unit tests for ogx_client serialization helpers."""

import json
from typing import Any

import pytest
from ogx_client.models.open_ai_response_object import OpenAIResponseObject
from ogx_client.models.open_ai_response_object_stream import (
    OpenAIResponseObjectStream,
)
from ogx_client.models.open_ai_response_object_stream_response_completed import (
    OpenAIResponseObjectStreamResponseCompleted,
)
from ogx_client.models.open_ai_response_object_stream_response_output_item_added import (
    OpenAIResponseObjectStreamResponseOutputItemAdded,
)

from models.api.responses.successful.responses_openai import ResponsesResponse
from utils.ogx_serialization import dump_ogx_model


@pytest.fixture(name="complex_client_response_payload")
def complex_client_response_payload_fixture() -> dict[str, Any]:
    """A response payload that exercises nested OneOf fields in ogx_client."""
    return {
        "id": "resp_complex",
        "object": "response",
        "created_at": 1_234_567_890,
        "status": "completed",
        "model": "provider/model",
        "store": False,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "input": "multi-step query with tools",
        "tools": [{"type": "file_search", "vector_store_ids": ["vs_1", "vs_2"]}],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "input_tokens_details": {"cached_tokens": 10},
            "output_tokens_details": {"reasoning_tokens": 5},
        },
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Searching docs...",
                        "annotations": [],
                    }
                ],
                "status": "completed",
                "id": "msg_1",
            },
            {
                "type": "file_search_call",
                "id": "fs_1",
                "status": "completed",
                "queries": ["lightspeed", "quota"],
                "results": [
                    {
                        "file_id": "file_abc",
                        "filename": "guide.pdf",
                        "score": 0.91,
                        "text": "relevant chunk",
                        "attributes": {"page": 2, "section": "limits"},
                    }
                ],
            },
            {
                "type": "function_call",
                "id": "fc_1",
                "call_id": "call_weather",
                "name": "get_weather",
                "arguments": '{"city":"NYC"}',
                "status": "completed",
            },
            {
                "type": "mcp_call",
                "id": "mcp_1",
                "status": "completed",
                "server_label": "portal",
                "name": "search",
                "arguments": "{}",
                "output": "portal result",
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Final answer.",
                        "annotations": [],
                    }
                ],
                "status": "completed",
                "id": "msg_2",
            },
        ],
    }


def test_dump_ogx_model_complex_client_response(
    complex_client_response_payload: dict[str, Any],
) -> None:
    """A multi-item client response must dump all OneOf-backed fields correctly."""
    response = OpenAIResponseObject.from_dict(complex_client_response_payload)

    dumped = dump_ogx_model(response)

    json.dumps(dumped)
    assert dumped["tool_choice"] == "auto"
    assert dumped["tools"] == [
        {"type": "file_search", "vector_store_ids": ["vs_1", "vs_2"]}
    ]
    assert [item["type"] for item in dumped["output"]] == [
        "message",
        "file_search_call",
        "function_call",
        "mcp_call",
        "message",
    ]
    assert dumped["output"][0]["content"][0]["text"] == "Searching docs..."
    assert dumped["output"][1]["results"][0]["attributes"] == {
        "page": 2,
        "section": "limits",
    }
    assert dumped["output"][2]["arguments"] == '{"city":"NYC"}'
    assert dumped["output"][3]["server_label"] == "portal"
    assert dumped["usage"]["input_tokens_details"]["cached_tokens"] == 10

    validated = ResponsesResponse.model_validate(
        {
            **dumped,
            "safety_identifier": "safety-id",
            "available_quotas": {},
            "conversation": "conv-id",
            "completed_at": 1,
            "output_text": "Final answer.",
        }
    )
    assert validated.tool_choice == "auto"
    assert validated.output_text == "Final answer."


def test_dump_ogx_model_model_dump_leaves_empty_oneof_wrappers(
    complex_client_response_payload: dict[str, Any],
) -> None:
    """Plain model_dump is the failure mode dump_ogx_model exists to fix."""
    response = OpenAIResponseObject.from_dict(complex_client_response_payload)

    broken = response.model_dump(exclude_none=True)
    fixed = dump_ogx_model(response)

    assert broken["tool_choice"] == {}
    assert fixed["tool_choice"] == "auto"

    added = OpenAIResponseObjectStreamResponseOutputItemAdded.from_dict(
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "sequence_number": 1,
            "response_id": "resp_complex",
            "item": complex_client_response_payload["output"][0],
        }
    )
    stream_chunk = OpenAIResponseObjectStream(actual_instance=added)

    broken_chunk = stream_chunk.model_dump(exclude_none=True, by_alias=True)
    fixed_chunk = dump_ogx_model(stream_chunk)

    assert broken_chunk["item"] == {}
    assert fixed_chunk["item"]["content"][0]["text"] == "Searching docs..."


def test_dump_ogx_model_complex_streaming_chunks(
    complex_client_response_payload: dict[str, Any],
) -> None:
    """Streaming wrappers must preserve nested tool-call and response payloads."""
    mcp_item = complex_client_response_payload["output"][3]
    added = OpenAIResponseObjectStreamResponseOutputItemAdded.from_dict(
        {
            "type": "response.output_item.added",
            "output_index": 3,
            "sequence_number": 4,
            "response_id": "resp_complex",
            "item": mcp_item,
        }
    )
    completed = OpenAIResponseObjectStreamResponseCompleted.from_dict(
        {
            "type": "response.completed",
            "sequence_number": 10,
            "response": complex_client_response_payload,
        }
    )

    added_dump = dump_ogx_model(OpenAIResponseObjectStream(actual_instance=added))
    completed_dump = dump_ogx_model(
        OpenAIResponseObjectStream(actual_instance=completed)
    )

    json.dumps(added_dump)
    json.dumps(completed_dump)

    assert added_dump["item"] == {
        "id": "mcp_1",
        "type": "mcp_call",
        "arguments": "{}",
        "name": "search",
        "server_label": "portal",
        "output": "portal result",
    }
    assert completed_dump["response"]["tool_choice"] == "auto"
    assert len(completed_dump["response"]["output"]) == 5
    assert completed_dump["response"]["output"][1]["results"][0]["filename"] == (
        "guide.pdf"
    )

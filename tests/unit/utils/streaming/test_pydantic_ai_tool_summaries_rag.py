"""Unit tests for pydantic-ai file-search RAG extraction in tool_summaries."""

from datetime import UTC, datetime

from openai.types.responses.response_file_search_tool_call import Result
from pydantic_ai.messages import ModelResponse, NativeToolReturnPart

from utils.streaming.pydantic_ai_tool_summaries import (
    parse_tool_rag_chunks_from_agent_messages,
    parse_tool_referenced_documents_from_agent_messages,
)


def _file_search_response(*, results: list[Result]) -> ModelResponse:
    """Build a model response containing a file-search tool return."""
    return ModelResponse(
        parts=[
            NativeToolReturnPart(
                tool_name="file_search",
                content={
                    "status": "completed",
                    "results": [r.model_dump(mode="json") for r in results],
                },
                tool_call_id="fs-1",
                timestamp=datetime.now(UTC),
            )
        ],
        model_name="gpt-4",
        timestamp=datetime.now(UTC),
    )


def test_parse_tool_rag_chunks_from_agent_messages() -> None:
    """OpenAI Result dumps in native returns become RAG chunks."""
    messages = [
        _file_search_response(
            results=[
                Result(
                    text="chunk one",
                    score=0.9,
                    attributes={"title": "Doc A", "url": "https://example.com/a"},
                ),
                Result(text="chunk two", score=0.5, attributes={"title": "Doc B"}),
            ]
        )
    ]
    chunks = parse_tool_rag_chunks_from_agent_messages(
        messages,
        vector_store_ids=["vs-1"],
        rag_id_mapping={"vs-1": "my-rag"},
    )
    assert len(chunks) == 2
    assert chunks[0].content == "chunk one"
    assert chunks[0].source == "my-rag"
    assert chunks[1].content == "chunk two"


def test_parse_tool_referenced_documents_from_agent_messages() -> None:
    """OpenAI result attributes become referenced documents."""
    messages = [
        _file_search_response(
            results=[
                Result(
                    text="ignored",
                    attributes={
                        "title": "Doc A",
                        "doc_url": "https://example.com/a",
                        "document_id": "id-a",
                    },
                ),
                Result(
                    text="duplicate",
                    attributes={
                        "title": "Doc A",
                        "doc_url": "https://example.com/a",
                    },
                ),
            ]
        )
    ]
    docs = parse_tool_referenced_documents_from_agent_messages(
        messages,
        vector_store_ids=["vs-1"],
        rag_id_mapping={},
    )
    assert len(docs) == 1
    assert docs[0].doc_title == "Doc A"
    assert str(docs[0].doc_url) == "https://example.com/a"
    assert docs[0].document_id == "id-a"


def test_parse_tool_rag_skips_return_without_results() -> None:
    """Status-only native returns yield nothing."""
    messages = [
        ModelResponse(
            parts=[
                NativeToolReturnPart(
                    tool_name="file_search",
                    content={"status": "in_progress"},
                    tool_call_id="fs-1",
                    timestamp=datetime.now(UTC),
                )
            ],
            model_name="gpt-4",
            timestamp=datetime.now(UTC),
        )
    ]
    assert not parse_tool_rag_chunks_from_agent_messages(messages)

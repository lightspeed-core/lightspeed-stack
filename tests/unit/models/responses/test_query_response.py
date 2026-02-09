"""Unit tests for QueryResponse model."""

from pydantic import AnyUrl

from models.responses import QueryResponse
from utils.types import ReferencedDocument, ToolCallSummary, ToolResultSummary


class TestQueryResponse:
    """Test cases for the QueryResponse model."""

    def test_constructor(self) -> None:
        """Test the QueryResponse constructor."""
        qr = QueryResponse(  # type: ignore[call-arg]
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
            response="LLM answer",
        )
        assert qr.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert qr.response == "LLM answer"

    def test_optional_conversation_id(self) -> None:
        """Test the QueryResponse with default conversation ID."""
        qr = QueryResponse(response="LLM answer")  # type: ignore[call-arg]
        assert qr.conversation_id is None
        assert qr.response == "LLM answer"

    def test_complete_query_response_with_all_fields(self) -> None:
        """Test QueryResponse with all fields including tool calls, and tool results."""
        tool_calls = [
            ToolCallSummary(
                id="call-1",
                name="knowledge_search",
                args={"query": "operator lifecycle manager"},
                type="tool_call",
            )
        ]
        tool_results = [
            ToolResultSummary(
                id="call-1",
                status="success",
                content='{"chunks_found": 5}',
                type="tool_result",
                round=1,
            )
        ]

        referenced_documents = [
            ReferencedDocument(
                doc_url=AnyUrl(
                    "https://docs.openshift.com/container-platform/4.15/operators/olm/index.html"
                ),
                doc_title="Operator Lifecycle Manager (OLM)",
            )
        ]

        qr = QueryResponse(
            conversation_id="123e4567-e89b-12d3-a456-426614174000",
            response="Operator Lifecycle Manager (OLM) helps users install...",
            tool_calls=tool_calls,
            tool_results=tool_results,
            referenced_documents=referenced_documents,
            truncated=False,
            input_tokens=100,
            output_tokens=50,
            available_quotas={"daily": 1000},
        )

        assert qr.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert qr.response == "Operator Lifecycle Manager (OLM) helps users install..."
        assert qr.tool_calls is not None
        assert len(qr.tool_calls) == 1
        assert qr.tool_calls[0].name == "knowledge_search"
        assert qr.tool_results is not None
        assert len(qr.tool_results) == 1
        assert qr.tool_results[0].status == "success"
        assert qr.tool_results[0].content == '{"chunks_found": 5}'
        assert qr.tool_results[0].type == "tool_result"
        assert qr.tool_results[0].round == 1
        assert len(qr.referenced_documents) == 1
        assert (
            qr.referenced_documents[0].doc_title == "Operator Lifecycle Manager (OLM)"
        )
        assert qr.truncated is False
        assert qr.input_tokens == 100
        assert qr.output_tokens == 50
        assert qr.available_quotas == {"daily": 1000}

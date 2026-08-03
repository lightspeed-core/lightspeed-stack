"""Unit tests for utils.agents.tool_processor module."""

import json

import pytest
from openai.types.responses.response_file_search_tool_call import (
    Result as OpenAIFileSearchResult,
)
from pydantic import AnyUrl
from pydantic_ai.messages import (
    NativeToolCallPart,
    NativeToolReturnPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.native_tools import FileSearchTool, MCPServerTool, WebSearchTool
from pytest_mock import MockerFixture

from lightspeed_stack.constants import DEFAULT_RAG_TOOL
from lightspeed_stack.models.common.agents import AgentTurnAccumulator
from lightspeed_stack.models.common.turn_summary import TurnSummary
from lightspeed_stack.utils.agents.tool_processor import (
    build_referenced_document,
    process_function_tool_call,
    process_function_tool_result,
    process_native_tool_call,
    process_native_tool_result,
    rag_chunks_from_file_search_results,
    referenced_documents_from_file_search_results,
    summarize_file_search_result,
    summarize_function_tool_call,
    summarize_function_tool_result,
    summarize_mcp_call_result,
    summarize_mcp_list_tools_result,
    summarize_mcp_tool_result,
    summarize_native_tool_call,
    summarize_web_search_result,
)


@pytest.fixture(name="turn_state")
def turn_state_fixture() -> AgentTurnAccumulator:
    """Create a fresh agent turn accumulator for dispatch tests."""
    return AgentTurnAccumulator(
        vector_store_ids=["vs-001"],
        rag_id_mapping={"vs-001": "ocp-docs"},
        turn_summary=TurnSummary(),
    )


def _file_search_result(**kwargs: object) -> OpenAIFileSearchResult:
    """Build a validated OpenAI file-search result row."""
    return OpenAIFileSearchResult.model_validate(kwargs)


class TestSummarizeFunctionToolCall:
    """Tests for summarize_function_tool_call."""

    def test_builds_function_call_summary(self) -> None:
        """Test function tool call is mapped to ToolCallSummary."""
        part = ToolCallPart(
            tool_name="my_fn",
            args={"key": "value"},
            tool_call_id="call-fn-1",
        )

        summary = summarize_function_tool_call(part)

        assert summary.id == "call-fn-1"
        assert summary.name == "my_fn"
        assert summary.args == {"key": "value"}
        assert summary.type == "function_call"


class TestSummarizeNativeToolCall:
    """Tests for summarize_native_tool_call."""

    def test_web_search_call(self) -> None:
        """Test web search native tool call summary."""
        part = NativeToolCallPart(
            tool_name=WebSearchTool.kind,
            args={"query": "OpenShift"},
            tool_call_id="ws-1",
        )

        summary = summarize_native_tool_call(part)

        assert summary is not None
        assert summary.type == "web_search_call"
        assert summary.name == WebSearchTool.kind

    def test_file_search_call(self) -> None:
        """Test file search native tool call uses DEFAULT_RAG_TOOL name."""
        part = NativeToolCallPart(
            tool_name=FileSearchTool.kind,
            args={"queries": ["docs"]},
            tool_call_id="fs-1",
        )

        summary = summarize_native_tool_call(part)

        assert summary is not None
        assert summary.name == DEFAULT_RAG_TOOL
        assert summary.type == "file_search_call"

    def test_mcp_list_tools_call(self) -> None:
        """Test MCP list-tools action summary."""
        part = NativeToolCallPart(
            tool_name=f"{MCPServerTool.kind}:srv",
            args={"action": "list_tools"},
            tool_call_id="mcp-list-1",
        )

        summary = summarize_native_tool_call(part)

        assert summary is not None
        assert summary.name == "mcp_list_tools"
        assert summary.args == {"server_label": "srv"}
        assert summary.type == "mcp_list_tools"

    def test_mcp_list_tools_call_with_label(self) -> None:
        """Test labeled MCP list-tools action uses the server label suffix."""
        part = NativeToolCallPart(
            tool_name=f"{MCPServerTool.kind}:myserver",
            args={"action": "list_tools"},
            tool_call_id="mcp-list-labeled",
        )

        summary = summarize_native_tool_call(part)

        assert summary is not None
        assert summary.args == {"server_label": "myserver"}

    def test_mcp_call(self) -> None:
        """Test MCP tool call summary."""
        part = NativeToolCallPart(
            tool_name=f"{MCPServerTool.kind}:srv",
            args={
                "action": "call",
                "tool_name": "remote_tool",
                "tool_args": {"arg": 1},
            },
            tool_call_id="mcp-call-1",
        )

        summary = summarize_native_tool_call(part)

        assert summary is not None
        assert summary.name == "remote_tool"
        assert summary.args == {"arg": 1}
        assert summary.type == "mcp_call"

    def test_unknown_tool_returns_none(self, mocker: MockerFixture) -> None:
        """Test unknown native tool logs warning and returns None."""
        mock_warning = mocker.patch(
            "lightspeed_stack.utils.agents.tool_processor.logger.warning"
        )
        part = NativeToolCallPart(
            tool_name="unknown_tool",
            args={},
            tool_call_id="unk-1",
        )

        assert summarize_native_tool_call(part) is None
        mock_warning.assert_called_once()


class TestProcessFunctionToolCall:
    """Tests for process_function_tool_call."""

    def test_records_tool_call_on_state(self, turn_state: AgentTurnAccumulator) -> None:
        """Test first function tool call is recorded on turn state."""
        part = ToolCallPart(
            tool_name="fn",
            args={"x": 1},
            tool_call_id="call-1",
        )

        summary = process_function_tool_call(turn_state, part)

        assert summary is not None
        assert turn_state.turn_summary.tool_calls == [summary]
        assert "call-1" in turn_state.emitted_tool_call_ids

    def test_skips_duplicate_tool_call(self, turn_state: AgentTurnAccumulator) -> None:
        """Test duplicate function tool call id is not recorded twice."""
        part = ToolCallPart(tool_name="fn", args={}, tool_call_id="call-dup")
        process_function_tool_call(turn_state, part)

        assert process_function_tool_call(turn_state, part) is None
        assert len(turn_state.turn_summary.tool_calls) == 1

    def test_increments_round_when_pending(
        self, turn_state: AgentTurnAccumulator
    ) -> None:
        """Test pending round increment runs before recording tool call."""
        turn_state.round_increment_pending = True
        turn_state.tool_round = 2
        part = ToolCallPart(tool_name="fn", args={}, tool_call_id="call-round")

        process_function_tool_call(turn_state, part)

        assert turn_state.tool_round == 3
        assert not turn_state.round_increment_pending


class TestProcessNativeToolCall:
    """Tests for process_native_tool_call."""

    def test_records_native_tool_call(self, turn_state: AgentTurnAccumulator) -> None:
        """Test native tool call is recorded on turn state."""
        part = NativeToolCallPart(
            tool_name=WebSearchTool.kind,
            args={"query": "q"},
            tool_call_id="ws-record",
        )

        summary = process_native_tool_call(turn_state, part)

        assert summary is not None
        assert turn_state.turn_summary.tool_calls == [summary]

    def test_skips_duplicate_and_unknown(
        self, turn_state: AgentTurnAccumulator, mocker: MockerFixture
    ) -> None:
        """Test duplicate ids and unknown tools are not recorded."""
        mocker.patch("lightspeed_stack.utils.agents.tool_processor.logger.warning")
        part = NativeToolCallPart(
            tool_name="unknown",
            args={},
            tool_call_id="unk-record",
        )

        assert process_native_tool_call(turn_state, part) is None
        assert not turn_state.turn_summary.tool_calls

        known = NativeToolCallPart(
            tool_name=WebSearchTool.kind,
            args={},
            tool_call_id="ws-dup",
        )
        process_native_tool_call(turn_state, known)
        assert process_native_tool_call(turn_state, known) is None


class TestSummarizeFunctionToolResult:
    """Tests for summarize_function_tool_result."""

    def test_builds_function_tool_result(self) -> None:
        """Test function tool return maps to ToolResultSummary."""
        part = ToolReturnPart(
            tool_name="fn",
            content={"answer": 42},
            tool_call_id="result-1",
        )

        result = summarize_function_tool_result(part, tool_round=3)

        assert result.id == "result-1"
        assert result.status == "success"
        assert result.type == "function_call_output"
        assert result.round == 3
        assert json.loads(result.content) == {"answer": 42}


class TestProcessFunctionToolResult:
    """Tests for process_function_tool_result."""

    def test_records_function_tool_result(
        self, turn_state: AgentTurnAccumulator
    ) -> None:
        """Test function tool result is recorded and marks round pending."""
        part = ToolReturnPart(
            tool_name="fn",
            content="ok",
            tool_call_id="result-record",
        )

        result = process_function_tool_result(turn_state, part)

        assert result is not None
        assert turn_state.turn_summary.tool_results == [result]
        assert turn_state.round_increment_pending
        assert "result-record" in turn_state.emitted_tool_result_ids

    def test_skips_duplicate_result(self, turn_state: AgentTurnAccumulator) -> None:
        """Test duplicate function tool result id is ignored."""
        part = ToolReturnPart(tool_name="fn", content="ok", tool_call_id="result-dup")
        process_function_tool_result(turn_state, part)

        assert process_function_tool_result(turn_state, part) is None
        assert len(turn_state.turn_summary.tool_results) == 1


class TestBuildReferencedDocument:
    """Tests for build_referenced_document."""

    def test_returns_none_without_title_or_url(self) -> None:
        """Test result without title or URL metadata is skipped."""
        result = _file_search_result(attributes={"document_id": "only-id"})

        assert build_referenced_document(result, ["vs-001"], {}) is None

    def test_builds_from_url_and_title_with_source_mapping(self) -> None:
        """Test referenced document resolves source from vector store mapping."""
        result = _file_search_result(
            attributes={
                "link": "https://example.com/doc",
                "title": "Example Doc",
                "document_id": "doc-1",
            }
        )

        doc = build_referenced_document(result, ["vs-001"], {"vs-001": "mapped-source"})

        assert doc is not None
        assert doc.doc_url == AnyUrl("https://example.com/doc")
        assert doc.doc_title == "Example Doc"
        assert doc.document_id == "doc-1"
        assert doc.source == "mapped-source"

    def test_supports_alternate_url_and_id_keys(self) -> None:
        """Test doc_url and doc_id attribute key fallbacks."""
        result = _file_search_result(
            attributes={
                "docs_url": "https://example.com/alt",
                "title": "Alt Doc",
                "doc_id": "alt-id",
            }
        )

        doc = build_referenced_document(result, [], {})

        assert doc is not None
        assert doc.doc_url == AnyUrl("https://example.com/alt")
        assert doc.document_id == "alt-id"

    def test_title_only_document(self) -> None:
        """Test referenced document can be built with title only."""
        result = _file_search_result(attributes={"title": "Title Only"})

        doc = build_referenced_document(result, [], {})

        assert doc is not None
        assert doc.doc_url is None
        assert doc.doc_title == "Title Only"


class TestReferencedDocumentsFromFileSearchResults:
    """Tests for referenced_documents_from_file_search_results."""

    def test_deduplicates_documents(self) -> None:
        """Test seen_docs prevents duplicate referenced documents."""
        results = [
            _file_search_result(attributes={"url": "https://dup.com", "title": "Same"}),
            _file_search_result(
                attributes={"link": "https://dup.com", "title": "Same"}
            ),
            _file_search_result(
                attributes={"url": "https://other.com", "title": "Other"}
            ),
            _file_search_result(attributes={"document_id": "no-metadata"}),
        ]
        seen_docs: set[tuple[str, str]] = set()

        documents = referenced_documents_from_file_search_results(
            results, seen_docs, ["vs-001"], {"vs-001": "source"}
        )

        assert len(documents) == 2
        assert len(seen_docs) == 2


class TestRagChunksFromFileSearchResults:
    """Tests for rag_chunks_from_file_search_results."""

    def test_skips_empty_text_and_maps_source(self) -> None:
        """Test chunks without text are skipped and source is resolved."""
        results = [
            _file_search_result(text="chunk one", score=0.8, attributes={}),
            _file_search_result(text="", score=0.5, attributes={}),
        ]

        chunks = rag_chunks_from_file_search_results(
            results, ["vs-001"], {"vs-001": "mapped"}
        )

        assert len(chunks) == 1
        assert chunks[0].content == "chunk one"
        assert chunks[0].source == "mapped"
        assert chunks[0].score == 0.8


class TestSummarizeWebSearchResult:
    """Tests for summarize_web_search_result."""

    def test_serializes_remaining_content(self) -> None:
        """Test web search result keeps non-status fields as JSON content."""
        part = NativeToolReturnPart(
            tool_name=WebSearchTool.kind,
            tool_call_id="ws-result",
            content={"status": "success", "results": [{"title": "hit"}]},
        )

        result = summarize_web_search_result(part, tool_round=1)

        assert result.status == "success"
        assert result.type == "web_search_call"
        assert json.loads(result.content) == {"results": [{"title": "hit"}]}

    def test_empty_content_when_only_status(self) -> None:
        """Test web search result content is empty when only status remains."""
        part = NativeToolReturnPart(
            tool_name=WebSearchTool.kind,
            tool_call_id="ws-empty",
            content={"status": "success"},
        )

        result = summarize_web_search_result(part, tool_round=2)

        assert not result.content


class TestSummarizeMcpResults:
    """Tests for MCP tool result summarizers."""

    def test_list_tools_success(self) -> None:
        """Test MCP list-tools success payload is serialized."""
        part = NativeToolReturnPart(
            tool_name=f"{MCPServerTool.kind}:srv",
            tool_call_id="mcp-list",
            content={
                "tools": [
                    {"name": "tool_a", "description": "does things"},
                ],
                "error": None,
            },
        )

        result = summarize_mcp_list_tools_result(part, tool_round=1)

        assert result.status == "success"
        assert result.type == "mcp_list_tools"
        payload = json.loads(result.content)
        assert payload["server_label"] == "srv"
        assert payload["tools"][0]["name"] == "tool_a"

    def test_list_tools_error(self) -> None:
        """Test MCP list-tools error returns failure summary."""
        part = NativeToolReturnPart(
            tool_name=f"{MCPServerTool.kind}:srv",
            tool_call_id="mcp-list-err",
            content={"tools": [], "error": "unavailable"},
        )

        result = summarize_mcp_list_tools_result(part, tool_round=1)

        assert result.status == "failure"
        assert result.content == "unavailable"

    def test_mcp_call_success_and_error(self) -> None:
        """Test MCP call success and error summaries."""
        success_part = NativeToolReturnPart(
            tool_name=f"{MCPServerTool.kind}:srv",
            tool_call_id="mcp-call-ok",
            content={"output": "done", "error": None},
        )
        error_part = NativeToolReturnPart(
            tool_name=f"{MCPServerTool.kind}:srv",
            tool_call_id="mcp-call-err",
            content={"output": None, "error": "failed"},
        )

        success = summarize_mcp_call_result(success_part, tool_round=2)
        error = summarize_mcp_call_result(error_part, tool_round=2)

        assert success.status == "success"
        assert success.content == "done"
        assert error.status == "failure"
        assert error.content == "failed"

    def test_mcp_tool_result_dispatches_by_shape(self) -> None:
        """Test summarize_mcp_tool_result routes pydantic-ai MCP return shapes."""
        list_part = NativeToolReturnPart(
            tool_name=f"{MCPServerTool.kind}:srv",
            tool_call_id="dispatch-list",
            content={"tools": [], "error": None},
        )
        call_part = NativeToolReturnPart(
            tool_name=f"{MCPServerTool.kind}:srv",
            tool_call_id="dispatch-call",
            content={"output": "ok", "error": None},
        )

        list_result = summarize_mcp_tool_result(list_part, tool_round=1)
        call_result = summarize_mcp_tool_result(call_part, tool_round=1)

        assert list_result.type == "mcp_list_tools"
        assert call_result.type == "mcp_call"

    def test_mcp_call_with_error_field_not_routed_to_list_tools(self) -> None:
        """Test MCP call returns are not misrouted when error is always present."""
        call_part = NativeToolReturnPart(
            tool_name=f"{MCPServerTool.kind}:srv",
            tool_call_id="dispatch-call-only-error",
            content={"output": "ok", "error": None},
        )

        result = summarize_mcp_tool_result(call_part, tool_round=1)

        assert result.type == "mcp_call"
        assert result.content == "ok"


class TestSummarizeFileSearchResult:
    """Tests for summarize_file_search_result."""

    def test_builds_tool_result_rag_chunks_and_referenced_docs(self) -> None:
        """Test file-search return produces result, chunks, and referenced docs."""
        part = NativeToolReturnPart(
            tool_name=FileSearchTool.kind,
            tool_call_id="fs-result",
            content={
                "status": "success",
                "results": [
                    {
                        "text": "chunk text",
                        "score": 0.95,
                        "attributes": {
                            "title": "Doc",
                            "url": "https://example.com",
                        },
                    },
                    {"text": "", "attributes": {}},
                ],
            },
        )
        seen_docs: set[tuple[str, str]] = set()

        tool_result, rag_chunks, referenced_docs = summarize_file_search_result(
            part,
            tool_round=4,
            seen_docs=seen_docs,
            vector_store_ids=["vs-001"],
            rag_id_mapping={"vs-001": "mapped"},
        )

        assert tool_result.status == "success"
        assert tool_result.type == "file_search_call"
        assert tool_result.round == 4
        assert len(rag_chunks) == 1
        assert rag_chunks[0].content == "chunk text"
        assert len(referenced_docs) == 1
        assert referenced_docs[0].doc_title == "Doc"
        assert len(seen_docs) == 1


class TestProcessNativeToolResult:
    """Tests for process_native_tool_result."""

    def test_records_file_search_result(self, turn_state: AgentTurnAccumulator) -> None:
        """Test file-search result updates tool results, RAG chunks, and docs."""
        part = NativeToolReturnPart(
            tool_name=FileSearchTool.kind,
            tool_call_id="fs-process",
            content={
                "status": "success",
                "results": [
                    {
                        "text": "rag",
                        "attributes": {"title": "RAG Doc", "url": "https://rag"},
                    }
                ],
            },
        )

        result = process_native_tool_result(turn_state, part)

        assert result is not None
        assert turn_state.turn_summary.tool_results == [result]
        assert len(turn_state.turn_summary.rag_chunks) == 1
        assert len(turn_state.turn_summary.referenced_documents) == 1
        assert turn_state.round_increment_pending

    def test_records_labeled_mcp_result(self, turn_state: AgentTurnAccumulator) -> None:
        """Test labeled MCP tool return is processed like unlabeled MCP returns."""
        part = NativeToolReturnPart(
            tool_name=f"{MCPServerTool.kind}:srv",
            tool_call_id="mcp-labeled",
            content={"output": "labeled-output", "error": None},
        )

        result = process_native_tool_result(turn_state, part)

        assert result is not None
        assert result.content == "labeled-output"

    def test_records_web_search_and_mcp_results(
        self, turn_state: AgentTurnAccumulator
    ) -> None:
        """Test web search and MCP results are recorded on turn state."""
        web_part = NativeToolReturnPart(
            tool_name=WebSearchTool.kind,
            tool_call_id="ws-process",
            content={"status": "success"},
        )
        mcp_part = NativeToolReturnPart(
            tool_name=f"{MCPServerTool.kind}:srv",
            tool_call_id="mcp-process",
            content={"output": "mcp-output", "error": None},
        )

        web_result = process_native_tool_result(turn_state, web_part)
        mcp_result = process_native_tool_result(turn_state, mcp_part)

        assert web_result is not None
        assert mcp_result is not None
        assert len(turn_state.turn_summary.tool_results) == 2

    def test_skips_duplicate_and_unknown(
        self, turn_state: AgentTurnAccumulator, mocker: MockerFixture
    ) -> None:
        """Test duplicate ids and unknown tool returns are ignored."""
        mocker.patch("lightspeed_stack.utils.agents.tool_processor.logger.warning")
        part = NativeToolReturnPart(
            tool_name="unknown",
            tool_call_id="unk-result",
            content={"status": "success"},
        )

        assert process_native_tool_result(turn_state, part) is None

        known = NativeToolReturnPart(
            tool_name=WebSearchTool.kind,
            tool_call_id="ws-dup-result",
            content={"status": "success"},
        )
        process_native_tool_result(turn_state, known)
        assert process_native_tool_result(turn_state, known) is None

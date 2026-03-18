"""Unit tests for functions and types defined in utils/types.py."""

import pytest
from llama_stack_api import ImageContentItem, TextContentItem, URL, _URLOrData
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolFileSearch as InputToolFileSearch,
    OpenAIResponseInputToolMCP as InputToolMCP,
)

from pydantic import AnyUrl, ValidationError

from utils.types import (
    ReferencedDocument,
    ResponsesApiParams,
    ToolCallSummary,
    ToolResultSummary,
    content_to_str,
)


class TestContentToStr:
    """Tests for content_to_str function."""

    def test_content_to_str_none(self) -> None:
        """Test content_to_str with None."""
        assert content_to_str(None) == ""

    def test_content_to_str_string(self) -> None:
        """Test content_to_str with string."""
        assert content_to_str("test string") == "test string"

    def test_content_to_str_text_content_item(self) -> None:
        """Test content_to_str with TextContentItem."""
        text_item = TextContentItem(text="text content")
        result = content_to_str(text_item)
        assert result == "text content"

    def test_content_to_str_image_content_item(self) -> None:
        """Test content_to_str with ImageContentItem."""
        image_item = ImageContentItem(
            image=_URLOrData(url=URL(uri="http://example.com/img.png"))
        )
        result = content_to_str(image_item)
        assert result == "<image>"

    def test_content_to_str_list(self) -> None:
        """Test content_to_str with list."""
        result = content_to_str(["item1", "item2", "item3"])
        assert result == "item1 item2 item3"

    def test_content_to_str_nested_list(self) -> None:
        """Test content_to_str with nested list."""
        text_item = TextContentItem(text="nested text")
        result = content_to_str(["outer", text_item, ["inner1", "inner2"]])
        assert "outer" in result
        assert "nested text" in result
        assert "inner1" in result
        assert "inner2" in result

    def test_content_to_str_mixed_types(self) -> None:
        """Test content_to_str with mixed types in list."""
        text_item = TextContentItem(text="text")
        result = content_to_str(["string", text_item, 123, None])
        assert "string" in result
        assert "text" in result
        assert "123" in result

    def test_content_to_str_other_type(self) -> None:
        """Test content_to_str with other type falls back to str()."""
        result = content_to_str(123)
        assert result == "123"


class TestToolCallSummary:
    """Test cases for ToolCallSummary type."""

    def test_constructor(self) -> None:
        """Test ToolCallSummary with all fields."""
        tool_call = ToolCallSummary(
            id="call-1",
            name="knowledge_search",
            args={"query": "test"},
            type="tool_call",
        )
        assert tool_call.id == "call-1"
        assert tool_call.name == "knowledge_search"
        assert tool_call.args == {"query": "test"}
        assert tool_call.type == "tool_call"

    def test_missing_required_fields(self) -> None:
        """Test ToolCallSummary raises ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            ToolCallSummary()  # type: ignore[call-arg]


class TestToolResultSummary:
    """Test cases for ToolResultSummary type."""

    def test_constructor(self) -> None:
        """Test ToolResultSummary with all fields."""
        tool_result = ToolResultSummary(
            id="call-1",
            status="success",
            content='{"chunks_found": 5}',
            type="tool_result",
            round=1,
        )
        assert tool_result.id == "call-1"
        assert tool_result.status == "success"
        assert tool_result.content == '{"chunks_found": 5}'
        assert tool_result.type == "tool_result"
        assert tool_result.round == 1

    def test_missing_required_fields(self) -> None:
        """Test ToolResultSummary raises ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            ToolResultSummary()  # type: ignore[call-arg]


class TestReferencedDocument:
    """Test cases for ReferencedDocument type."""

    def test_constructor(self) -> None:
        """Test ReferencedDocument with all fields."""
        doc = ReferencedDocument(
            doc_url=AnyUrl("https://example.com/doc"),
            doc_title="Test Document",
        )
        assert str(doc.doc_url) == "https://example.com/doc"
        assert doc.doc_title == "Test Document"

    def test_constructor_with_defaults(self) -> None:
        """Test ReferencedDocument with no arguments uses None defaults."""
        doc = ReferencedDocument()
        assert doc.doc_url is None
        assert doc.doc_title is None

    def test_constructor_partial_fields(self) -> None:
        """Test ReferencedDocument with partial fields."""
        doc = ReferencedDocument(doc_url=AnyUrl("https://example.com/doc"))
        assert str(doc.doc_url) == "https://example.com/doc"
        assert doc.doc_title is None

        doc = ReferencedDocument(doc_title="Test Title")
        assert doc.doc_url is None
        assert doc.doc_title == "Test Title"


class TestResponsesApiParamsModelDump:
    """Tests for ResponsesApiParams.model_dump() MCP authorization fix.

    Regression tests for LCORE-1414 / GitHub issue #1269: llama-stack-api's
    InputToolMCP.authorization has Field(exclude=True), causing the base
    model_dump() to silently strip authorization tokens.
    """

    def _make_params(self, tools: list) -> ResponsesApiParams:
        """Build minimal ResponsesApiParams with given tools."""
        return ResponsesApiParams(
            input="test question",
            model="provider/model",
            conversation="conv-id",
            store=False,
            stream=False,
            tools=tools,
        )

    def test_mcp_authorization_survives_model_dump(self) -> None:
        """Test that MCP authorization is re-injected after model_dump()."""
        tool = InputToolMCP(
            server_label="auth-server",
            server_url="http://localhost:3000",
            require_approval="never",
            authorization="my-secret-token",
        )
        assert tool.authorization == "my-secret-token"
        assert "authorization" not in tool.model_dump()

        params = self._make_params([tool])
        dumped = params.model_dump(exclude_none=True)
        assert dumped["tools"][0]["authorization"] == "my-secret-token"

    def test_mcp_authorization_none_not_injected(self) -> None:
        """Test that None authorization is not added to the dump."""
        tool = InputToolMCP(
            server_label="no-auth-server",
            server_url="http://localhost:3000",
            require_approval="never",
        )
        params = self._make_params([tool])
        dumped = params.model_dump(exclude_none=True)
        assert "authorization" not in dumped["tools"][0]

    def test_non_mcp_tools_unaffected(self) -> None:
        """Test that non-MCP tools are not modified by the override."""
        tool = InputToolFileSearch(
            type="file_search",
            vector_store_ids=["vs-1"],
        )
        params = self._make_params([tool])
        dumped = params.model_dump(exclude_none=True)
        assert "authorization" not in dumped["tools"][0]

    def test_mixed_tools_only_mcp_gets_authorization(self) -> None:
        """Test mixed tool list: only MCP tools get authorization re-injected."""
        mcp_tool = InputToolMCP(
            server_label="auth-server",
            server_url="http://localhost:3000",
            require_approval="never",
            authorization="secret",
        )
        file_tool = InputToolFileSearch(
            type="file_search",
            vector_store_ids=["vs-1"],
        )
        params = self._make_params([file_tool, mcp_tool])
        dumped = params.model_dump(exclude_none=True)

        assert "authorization" not in dumped["tools"][0]
        assert dumped["tools"][1]["authorization"] == "secret"

    def test_multiple_mcp_tools_each_preserves_authorization(self) -> None:
        """Test that each MCP tool gets its own authorization re-injected."""
        tool_a = InputToolMCP(
            server_label="server-a",
            server_url="http://a:3000",
            require_approval="never",
            authorization="token-a",
        )
        tool_b = InputToolMCP(
            server_label="server-b",
            server_url="http://b:3000",
            require_approval="never",
            authorization="token-b",
        )
        params = self._make_params([tool_a, tool_b])
        dumped = params.model_dump(exclude_none=True)

        assert dumped["tools"][0]["authorization"] == "token-a"
        assert dumped["tools"][1]["authorization"] == "token-b"

    def test_exclude_changing_tool_list_shape_skips_reinjection(self) -> None:
        """Test that exclude removing tool indices does not mis-assign authorization."""
        tool_a = InputToolMCP(
            server_label="server-a",
            server_url="http://a:3000",
            require_approval="never",
            authorization="token-a",
        )
        tool_b = InputToolMCP(
            server_label="server-b",
            server_url="http://b:3000",
            require_approval="never",
            authorization="token-b",
        )
        params = self._make_params([tool_a, tool_b])
        dumped = params.model_dump(exclude={"tools": {0}})
        assert len(dumped["tools"]) == 1
        assert dumped["tools"][0]["server_label"] == "server-b"
        assert "authorization" not in dumped["tools"][0]

    def test_no_tools_does_not_error(self) -> None:
        """Test that model_dump() works when tools is None."""
        params = ResponsesApiParams(
            input="test",
            model="provider/model",
            conversation="conv-id",
            store=False,
            stream=False,
            tools=None,
        )
        dumped = params.model_dump(exclude_none=True)
        assert "tools" not in dumped

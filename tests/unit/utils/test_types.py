"""Unit tests for functions defined in utils/types.py."""

import json

from pytest_mock import MockerFixture

from constants import DEFAULT_RAG_TOOL
from utils.types import GraniteToolParser, TurnSummary


class TestGraniteToolParser:
    """Unit tests for functions defined in utils/types.py."""

    def test_get_tool_parser_when_model_is_is_not_granite(self) -> None:
        """Test that the tool_parser is None when model_id is not a granite model."""
        assert (
            GraniteToolParser.get_parser("ollama3.3") is None
        ), "tool_parser should be None"

    def test_get_tool_parser_when_model_id_does_not_start_with_granite(self) -> None:
        """Test that the tool_parser is None when model_id does not start with granite."""
        assert (
            GraniteToolParser.get_parser("a-fine-trained-granite-model") is None
        ), "tool_parser should be None"

    def test_get_tool_parser_when_model_id_starts_with_granite(self) -> None:
        """Test that the tool_parser is not None when model_id starts with granite."""
        tool_parser = GraniteToolParser.get_parser("granite-3.3-8b-instruct")
        assert tool_parser is not None, "tool_parser should not be None"

    def test_get_tool_calls_from_completion_message_when_none(self) -> None:
        """Test that get_tool_calls returns an empty array when CompletionMessage is None."""
        tool_parser = GraniteToolParser.get_parser("granite-3.3-8b-instruct")
        assert tool_parser is not None, "tool parser was not returned"
        assert tool_parser.get_tool_calls(None) == [], "get_tool_calls should return []"

    def test_get_tool_calls_from_completion_message_when_not_none(
        self, mocker: MockerFixture
    ) -> None:
        """Test that get_tool_calls returns an empty array when CompletionMessage has no tool_calls."""  # pylint: disable=line-too-long
        tool_parser = GraniteToolParser.get_parser("granite-3.3-8b-instruct")
        assert tool_parser is not None, "tool parser was not returned"
        completion_message = mocker.Mock()
        completion_message.tool_calls = []
        assert not tool_parser.get_tool_calls(
            completion_message
        ), "get_tool_calls should return []"

    def test_get_tool_calls_from_completion_message_when_message_has_tool_calls(
        self, mocker: MockerFixture
    ) -> None:
        """Test that get_tool_calls returns the tool_calls when CompletionMessage has tool_calls."""
        tool_parser = GraniteToolParser.get_parser("granite-3.3-8b-instruct")
        assert tool_parser is not None, "tool parser was not returned"
        completion_message = mocker.Mock()
        tool_calls = [mocker.Mock(tool_name="tool-1"), mocker.Mock(tool_name="tool-2")]
        completion_message.tool_calls = tool_calls
        assert (
            tool_parser.get_tool_calls(completion_message) == tool_calls
        ), f"get_tool_calls should return {tool_calls}"


class TestTurnSummaryExtractRagChunks:
    """Unit tests for TurnSummary._extract_rag_chunks_from_response."""

    def _create_turn_summary(self) -> TurnSummary:
        """Create a TurnSummary instance for testing."""
        return TurnSummary(llm_response="test response", tool_calls=[])

    def test_empty_response(self) -> None:
        """Test that empty response produces no chunks."""
        summary = self._create_turn_summary()
        summary._extract_rag_chunks_from_response("")
        assert len(summary.rag_chunks) == 0

    def test_whitespace_only_response(self) -> None:
        """Test that whitespace-only response produces no chunks."""
        summary = self._create_turn_summary()
        summary._extract_rag_chunks_from_response("   \n\t  ")
        assert len(summary.rag_chunks) == 0

    def test_json_dict_with_chunks(self) -> None:
        """Test parsing JSON dict with chunks array."""
        summary = self._create_turn_summary()
        response = json.dumps(
            {
                "chunks": [
                    {"content": "Chunk 1 content", "source": "doc1.md", "score": 0.95},
                    {"content": "Chunk 2 content", "source": "doc2.md", "score": 0.85},
                ]
            }
        )
        summary._extract_rag_chunks_from_response(response)

        assert len(summary.rag_chunks) == 2
        assert summary.rag_chunks[0].content == "Chunk 1 content"
        assert summary.rag_chunks[0].source == "doc1.md"
        assert summary.rag_chunks[0].score == 0.95
        assert summary.rag_chunks[1].content == "Chunk 2 content"
        assert summary.rag_chunks[1].source == "doc2.md"
        assert summary.rag_chunks[1].score == 0.85

    def test_json_list_of_chunks(self) -> None:
        """Test parsing JSON list of chunk objects."""
        summary = self._create_turn_summary()
        response = json.dumps(
            [
                {"content": "First chunk", "source": "source1"},
                {"content": "Second chunk", "source": "source2"},
            ]
        )
        summary._extract_rag_chunks_from_response(response)

        assert len(summary.rag_chunks) == 2
        assert summary.rag_chunks[0].content == "First chunk"
        assert summary.rag_chunks[1].content == "Second chunk"

    def test_formatted_text_single_result(self) -> None:
        """Test parsing formatted text with single Result block."""
        summary = self._create_turn_summary()
        response = """knowledge_search tool found 1 chunks:
BEGIN of knowledge_search tool results.
 Result 1
Content: This is the content of the first chunk.
Metadata: {'chunk_id': 'abc123', 'document_id': 'doc1', 'docs_url': 'https://example.com/doc1', 'title': 'Example Doc'}
END of knowledge_search tool results.
"""
        summary._extract_rag_chunks_from_response(response)

        assert len(summary.rag_chunks) == 1
        assert summary.rag_chunks[0].content == "This is the content of the first chunk."
        assert summary.rag_chunks[0].source == "https://example.com/doc1"

    def test_formatted_text_multiple_results(self) -> None:
        """Test parsing formatted text with multiple Result blocks."""
        summary = self._create_turn_summary()
        response = """knowledge_search tool found 3 chunks:
BEGIN of knowledge_search tool results.
 Result 1
Content: First chunk content here.
Metadata: {'chunk_id': 'id1', 'docs_url': 'https://docs.example.com/page1', 'title': 'Page 1'}
 Result 2
Content: Second chunk with more text.
Metadata: {'chunk_id': 'id2', 'docs_url': 'https://docs.example.com/page2', 'title': 'Page 2'}
 Result 3
Content: Third and final chunk.
Metadata: {'chunk_id': 'id3', 'source': 'https://docs.example.com/page3', 'title': 'Page 3'}
END of knowledge_search tool results.
"""
        summary._extract_rag_chunks_from_response(response)

        assert len(summary.rag_chunks) == 3
        assert summary.rag_chunks[0].content == "First chunk content here."
        assert summary.rag_chunks[0].source == "https://docs.example.com/page1"
        assert summary.rag_chunks[1].content == "Second chunk with more text."
        assert summary.rag_chunks[1].source == "https://docs.example.com/page2"
        assert summary.rag_chunks[2].content == "Third and final chunk."
        # Falls back to 'source' when 'docs_url' is not present
        assert summary.rag_chunks[2].source == "https://docs.example.com/page3"

    def test_formatted_text_multiline_content(self) -> None:
        """Test parsing formatted text with multiline content."""
        summary = self._create_turn_summary()
        response = """knowledge_search tool found 1 chunks:
BEGIN of knowledge_search tool results.
 Result 1
Content: # Heading

This is a paragraph with multiple lines.

* Bullet point 1
* Bullet point 2

More text here.
Metadata: {'chunk_id': 'multi1', 'docs_url': 'https://example.com/multiline'}
END of knowledge_search tool results.
"""
        summary._extract_rag_chunks_from_response(response)

        assert len(summary.rag_chunks) == 1
        assert "# Heading" in summary.rag_chunks[0].content
        assert "* Bullet point 1" in summary.rag_chunks[0].content
        assert "More text here." in summary.rag_chunks[0].content

    def test_formatted_text_without_metadata(self) -> None:
        """Test parsing formatted text when metadata parsing fails."""
        summary = self._create_turn_summary()
        response = """knowledge_search tool found 1 chunks:
BEGIN of knowledge_search tool results.
 Result 1
Content: Content without valid metadata.
Metadata: {invalid json here}
END of knowledge_search tool results.
"""
        summary._extract_rag_chunks_from_response(response)

        assert len(summary.rag_chunks) == 1
        assert summary.rag_chunks[0].content == "Content without valid metadata."
        assert summary.rag_chunks[0].source is None

    def test_fallback_to_single_chunk(self) -> None:
        """Test fallback to treating response as single chunk."""
        summary = self._create_turn_summary()
        response = "This is just plain text without any special formatting."
        summary._extract_rag_chunks_from_response(response)

        assert len(summary.rag_chunks) == 1
        assert summary.rag_chunks[0].content == response
        assert summary.rag_chunks[0].source == DEFAULT_RAG_TOOL
        assert summary.rag_chunks[0].score is None

    def test_real_world_response_format(self) -> None:
        """Test with real-world formatted response from knowledge_search."""
        summary = self._create_turn_summary()
        response = """knowledge_search tool found 2 chunks:
BEGIN of knowledge_search tool results.
 Result 1
Content: # JobSet Operator overview

Use the JobSet Operator on Red Hat OpenShift Container Platform to easily manage and run large-scale, coordinated workloads.

[IMPORTANT]
----
JobSet Operator is a Technology Preview feature only.
----
Metadata: {'chunk_id': '901a76d0-dc86-438b-91a3-bfac880a0c17', 'document_id': '8a84b126-46ae-454d-a752-c21ea121cb0d', 'source': 'https://docs.openshift.com/container-platform//4.19', 'docs_url': 'https://docs.openshift.com/container-platform//4.19', 'title': 'JobSet Operator overview', 'url_reachable': False}
 Result 2
Content: The JobSet Operator automatically sets up stable headless service.
Metadata: {'chunk_id': '1240732d-33b5-4900-baeb-d63306c97080', 'document_id': '8a84b126-46ae-454d-a752-c21ea121cb0d', 'source': 'https://docs.openshift.com/container-platform//4.19', 'docs_url': 'https://docs.openshift.com/container-platform//4.19', 'title': 'JobSet Operator overview', 'url_reachable': False}
END of knowledge_search tool results.
 The above results were retrieved to help answer the user's query.
"""
        summary._extract_rag_chunks_from_response(response)

        assert len(summary.rag_chunks) == 2
        assert "# JobSet Operator overview" in summary.rag_chunks[0].content
        assert "Technology Preview" in summary.rag_chunks[0].content
        assert (
            summary.rag_chunks[0].source
            == "https://docs.openshift.com/container-platform//4.19"
        )
        assert "stable headless service" in summary.rag_chunks[1].content
        assert (
            summary.rag_chunks[1].source
            == "https://docs.openshift.com/container-platform//4.19"
        )

    def test_json_with_optional_fields(self) -> None:
        """Test parsing JSON chunks with missing optional fields."""
        summary = self._create_turn_summary()
        response = json.dumps(
            {"chunks": [{"content": "Content only, no source or score"}]}
        )
        summary._extract_rag_chunks_from_response(response)

        assert len(summary.rag_chunks) == 1
        assert summary.rag_chunks[0].content == "Content only, no source or score"
        assert summary.rag_chunks[0].source is None
        assert summary.rag_chunks[0].score is None

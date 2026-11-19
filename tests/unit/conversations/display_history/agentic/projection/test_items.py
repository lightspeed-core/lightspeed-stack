"""Tests for projecting agent run messages into turn items."""

import pytest
from pydantic_ai.messages import (
    BinaryContent,
    BinaryImage,
    DocumentUrl,
    FilePart,
    ImageUrl,
    ModelMessage,
    ModelRequest,
    ModelRequestPart,
    ModelResponse,
    ModelResponsePart,
    TextContent,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UploadedFile,
    UserPromptPart,
)

from conversations.display_history.agentic.models.content import (
    FileContentPart,
    ImageContentPart,
    TextContentPart,
)
from conversations.display_history.agentic.models.turn_items import (
    MessageTurnItem,
    ReasoningTurnItem,
    ToolCallTurnItem,
    ToolResultTurnItem,
)
from conversations.display_history.agentic.projection.items import (
    turn_items_from_messages,
)
from knowledge.types import KnowledgeMatch


def _request(*parts: ModelRequestPart) -> ModelRequest:
    return ModelRequest(parts=parts)


def _response(*parts: ModelResponsePart, finish_reason: str = "stop") -> ModelResponse:
    return ModelResponse(parts=parts, finish_reason=finish_reason)  # type: ignore[arg-type]


def _project(
    *messages: ModelMessage,
) -> tuple[list, list, list]:
    return turn_items_from_messages(list(messages))


class TestInputOutputSplit:
    """Request parts before the first response are input."""

    def test_user_and_assistant_text(self) -> None:
        """A user prompt is input; assistant text is output."""
        input_items, output_items, documents = _project(
            _request(UserPromptPart(content="hi")),
            _response(TextPart(content="there")),
        )
        assert len(input_items) == 1
        assert len(output_items) == 1
        assert not documents
        assert isinstance(input_items[0], MessageTurnItem)
        assert input_items[0].role == "user"
        assert input_items[0].content == [TextContentPart(text="hi")]
        assert isinstance(output_items[0], MessageTurnItem)
        assert output_items[0].role == "assistant"
        assert output_items[0].id.startswith("msg_")

    def test_tool_return_before_first_response_is_input(self) -> None:
        """A deferred tool reply on the opening request is input."""
        input_items, output_items, _ = _project(
            _request(
                ToolReturnPart(
                    tool_name="get_weather",
                    content="sunny",
                    tool_call_id="call_1",
                )
            ),
            _response(TextPart(content="ok")),
        )
        assert isinstance(input_items[0], ToolResultTurnItem)
        assert input_items[0].content == "sunny"
        assert isinstance(output_items[0], MessageTurnItem)

    def test_empty_user_prompt_is_omitted(self) -> None:
        """Blank user text does not create a message item."""
        input_items, _, _ = _project(_request(UserPromptPart(content="")))
        assert not input_items


class TestAssistantParts:
    """Response parts become ordered output items."""

    def test_consecutive_text_parts_stay_separate(self) -> None:
        """Each assistant text segment becomes its own message."""
        _, output_items, _ = _project(
            _response(TextPart(content="Hello "), TextPart(content="world")),
        )
        assert [item.content for item in output_items] == [
            [TextContentPart(text="Hello ")],
            [TextContentPart(text="world")],
        ]

    def test_text_around_tool_call_keeps_order(self) -> None:
        """Assistant text stays in part order around tool calls."""
        _, output_items, _ = _project(
            _response(
                TextPart(content="before"),
                ToolCallPart(tool_name="ping", args={}, tool_call_id="call_p"),
                TextPart(content="after"),
            ),
        )
        assert [item.kind for item in output_items] == [
            "message",
            "tool_call",
            "message",
        ]

    def test_thinking_part_becomes_reasoning_item(self) -> None:
        """Model thinking is stored as a reasoning item."""
        _, output_items, _ = _project(
            _response(ThinkingPart(content="step by step", id="th_1")),
        )
        assert isinstance(output_items[0], ReasoningTurnItem)
        assert output_items[0].id == "th_1"
        assert output_items[0].content == "step by step"

    def test_image_file_part_is_an_assistant_message(self) -> None:
        """Assistant image attachments are kept; other file attachments are skipped."""
        image = BinaryImage(data=b"\xff\xd8\xff", media_type="image/jpeg")
        _, output_items, _ = _project(
            _response(
                TextPart(content="here"),
                FilePart(content=image),
                FilePart(
                    content=BinaryContent(data=b"pdf", media_type="application/pdf")
                ),
            )
        )
        assert len(output_items) == 2
        assert output_items[0].content == [TextContentPart(text="here")]
        part = output_items[1].content[0]
        assert isinstance(part, ImageContentPart)
        assert str(part.image_url) == image.data_uri
        assert part.media_type == "image/jpeg"


class TestToolClassification:
    """Wire names map onto display names and tool families."""

    @pytest.mark.parametrize(
        ("tool_name", "display_name", "toolset_type"),
        [
            ("get_weather", "get_weather", "function"),
            ("load_skill", "load_skill", "skills"),
            ("mcp_lookup_topic", "lookup_topic", "mcp"),
            ("search_knowledge", "search_knowledge", "file_search"),
        ],
    )
    def test_call_and_result_use_the_same_family(
        self, tool_name: str, display_name: str, toolset_type: str
    ) -> None:
        """Call and result share display name and toolset type."""
        _, output_items, _ = _project(
            _response(
                ToolCallPart(
                    tool_name=tool_name, args={"q": "x"}, tool_call_id="call_1"
                )
            ),
            _request(
                ToolReturnPart(tool_name=tool_name, content="ok", tool_call_id="call_1")
            ),
        )
        assert len(output_items) == 2
        call = output_items[0]
        result = output_items[1]
        assert isinstance(call, ToolCallTurnItem)
        assert call.name == display_name
        assert call.toolset.type == toolset_type
        assert call.call_id == "call_1"
        assert isinstance(result, ToolResultTurnItem)
        assert result.name == display_name
        assert result.toolset.type == toolset_type
        assert result.content == "ok"
        assert result.status == "success"

    def test_dict_tool_result_stays_a_dict(self) -> None:
        """JSON-object tool returns are kept as dicts."""
        input_items, _, _ = _project(
            _request(
                ToolReturnPart(
                    tool_name="get_weather",
                    content={"temp": 12},
                    tool_call_id="call_1",
                )
            )
        )
        assert isinstance(input_items[0], ToolResultTurnItem)
        assert input_items[0].content == {"temp": 12}


class TestKnowledgeCitations:
    """Knowledge search tool returns produce turn citations."""

    def test_matches_become_tool_result_and_documents(self) -> None:
        """Search matches appear on the tool result and as cited documents."""
        match = KnowledgeMatch(
            content="Cluster networking.",
            score=0.8,
            source="https://docs.example/network",
            metadata={"title": "Networking", "knowledge_source": "byok"},
        )
        _, output_items, documents = _project(
            _response(
                ToolCallPart(
                    tool_name="search_knowledge",
                    args={"query": "network"},
                    tool_call_id="call_k",
                )
            ),
            _request(
                ToolReturnPart(
                    tool_name="search_knowledge",
                    content=[match],
                    tool_call_id="call_k",
                )
            ),
        )
        result = output_items[1]
        assert isinstance(result, ToolResultTurnItem)
        assert result.toolset.type == "file_search"
        assert isinstance(result.content, list)
        assert result.content[0]["content"] == "Cluster networking."
        assert documents[0].doc_title == "Networking"
        assert documents[0].source == "byok"
        assert str(documents[0].doc_url) == "https://docs.example/network"

    def test_citation_needs_title_or_url(self) -> None:
        """Empty matches and matches without a title or URL are not cited."""
        _, _, documents = _project(
            _request(
                ToolReturnPart(
                    tool_name="search_knowledge",
                    content=[
                        KnowledgeMatch(
                            content="",
                            score=1.0,
                            source="https://docs.example/empty",
                            metadata={"title": "Empty"},
                        ),
                        KnowledgeMatch(content="No citation metadata.", score=0.1),
                        KnowledgeMatch(
                            content="Kept.",
                            score=0.5,
                            source="https://docs.example/kept",
                            metadata={"title": "Kept"},
                        ),
                    ],
                    tool_call_id="call_k",
                )
            )
        )
        assert len(documents) == 1
        assert documents[0].doc_title == "Kept"

    def test_citation_url_can_come_from_metadata(self) -> None:
        """A match source that is not a URL can still cite via metadata."""
        _, _, documents = _project(
            _request(
                ToolReturnPart(
                    tool_name="search_knowledge",
                    content=[
                        KnowledgeMatch(
                            content="Kept.",
                            score=1.0,
                            source="byok",
                            metadata={
                                "title": "Kept",
                                "url": "https://docs.example/kept",
                            },
                        )
                    ],
                    tool_call_id="call_k",
                )
            )
        )
        assert str(documents[0].doc_url) == "https://docs.example/kept"

    def test_duplicate_citations_are_dropped(self) -> None:
        """The same title and URL appear once."""
        match = KnowledgeMatch(
            content="a",
            score=1.0,
            source="https://docs.example/a",
            metadata={"title": "Doc A"},
        )
        _, _, documents = _project(
            _request(
                ToolReturnPart(
                    tool_name="search_knowledge",
                    content=[match, match],
                    tool_call_id="call_k",
                )
            )
        )
        assert len(documents) == 1

    def test_other_tools_do_not_emit_citations(self) -> None:
        """Only the knowledge search tool adds citations from matches."""
        _, _, documents = _project(
            _request(
                ToolReturnPart(
                    tool_name="not_search_knowledge",
                    content=[
                        KnowledgeMatch(
                            content="Chunk",
                            score=1.0,
                            source="https://docs.example/a",
                            metadata={"title": "Doc A"},
                        )
                    ],
                    tool_call_id="call_1",
                )
            )
        )
        assert not documents


class TestUserContent:
    """User prompt parts map onto display content."""

    def test_text_content_and_image_url(self) -> None:
        """User text and image URLs become message parts."""
        input_items, _, _ = _project(
            _request(
                UserPromptPart(
                    content=[
                        TextContent(content="see this"),
                        ImageUrl(
                            url="https://example.com/a.png",
                            media_type="image/png",
                        ),
                    ]
                )
            )
        )
        text, image = input_items[0].content
        assert text == TextContentPart(text="see this")
        assert isinstance(image, ImageContentPart)
        assert str(image.image_url) == "https://example.com/a.png"
        assert image.media_type == "image/png"

    def test_binary_image_uses_data_uri(self) -> None:
        """Inline image bytes are stored as a data URI."""
        binary = BinaryImage(data=b"\xff\xd8\xff", media_type="image/jpeg")
        input_items, _, _ = _project(_request(UserPromptPart(content=[binary])))
        image = input_items[0].content[0]
        assert isinstance(image, ImageContentPart)
        assert str(image.image_url) == binary.data_uri
        assert image.media_type == "image/jpeg"

    def test_uploaded_file_image_uses_file_id(self) -> None:
        """Provider-hosted images use file_id; other uploads stay files."""
        input_items, _, _ = _project(
            _request(
                UserPromptPart(
                    content=[
                        UploadedFile(
                            file_id="file-img",
                            provider_name="openai",
                            media_type="image/png",
                        ),
                        UploadedFile(
                            file_id="file-doc",
                            provider_name="openai",
                        ),
                    ]
                )
            )
        )
        image, document = input_items[0].content
        assert isinstance(image, ImageContentPart)
        assert image.file_id == "file-img"
        assert image.media_type == "image/png"
        assert isinstance(document, FileContentPart)
        assert document.file_id == "file-doc"

    def test_document_url_uses_path_basename(self) -> None:
        """Document URLs are stored as a file named after the path basename."""
        input_items, _, _ = _project(
            _request(
                UserPromptPart(
                    content=[DocumentUrl(url="https://example.com/docs/guide.pdf")]
                )
            )
        )
        assert input_items[0].content == [
            FileContentPart(filename="guide.pdf"),
        ]

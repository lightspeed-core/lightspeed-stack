"""Project agent run messages into display-history turn items."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Final, Optional
from urllib.parse import urlparse

from pydantic import AnyUrl, ValidationError
from pydantic_ai.messages import (
    BinaryContent,
    DocumentUrl,
    FilePart,
    ImageUrl,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextContent,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnContent,
    ToolReturnPart,
    UploadedFile,
    UserContent,
    UserPromptPart,
)

from conversations.agent_history.ids import new_id
from conversations.display_history.agentic.models.content import (
    FileContentPart,
    ImageContentPart,
    MessageContent,
    MessageContentPart,
    TextContentPart,
)
from conversations.display_history.agentic.models.turn_items import (
    MessageTurnItem,
    ReasoningTurnItem,
    ToolCallTurnItem,
    ToolResultTurnItem,
    ToolsetInfo,
    TurnItem,
)
from conversations.display_history.agentic.models.types import ToolResultBody
from knowledge.types import KnowledgeMatch
from models.common.turn_summary import ReferencedDocument

_IMAGE_MEDIA_PREFIX: Final[str] = "image/"
_MCP_NAME_PREFIX: Final[str] = "mcp_"
_KNOWLEDGE_TOOL_NAME: Final[str] = "search_knowledge"
_SKILLS_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {"list_skills", "load_skill", "read_skill_resource", "run_skill_script"}
)
_KNOWLEDGE_URL_KEYS: Final[tuple[str, ...]] = (
    "doc_url",
    "docs_url",
    "url",
    "reference_url",
)


def turn_items_from_messages(
    messages: list[ModelMessage],
) -> tuple[list[TurnItem], list[TurnItem], list[ReferencedDocument]]:
    """Split one agent run into input items, output items, and citations.

    Parts before the first model response are input. Everything from that
    response onward is output, including tool returns on later requests.

    Args:
        messages: New messages from one agent run.

    Returns:
        Input items, output items, and documents cited by knowledge search.

    """
    input_items: list[TurnItem] = []
    output_items: list[TurnItem] = []
    documents: list[ReferencedDocument] = []
    seen_response = False

    for message in messages:
        if isinstance(message, ModelResponse):
            seen_response = True
            message_items, cited_documents = _items_from_response(message)
            output_items.extend(message_items)
            documents.extend(cited_documents)
        elif isinstance(message, ModelRequest):
            message_items, cited_documents = _items_from_request(message)
            target = output_items if seen_response else input_items
            target.extend(message_items)
            documents.extend(cited_documents)

    return input_items, output_items, documents


def _items_from_request(
    message: ModelRequest,
) -> tuple[list[TurnItem], list[ReferencedDocument]]:
    """Convert user prompts and tool returns on a request.

    Args:
        message: Request message from the agent run.

    Returns:
        Turn items and citations found on this request.

    """
    items: list[TurnItem] = []
    documents: list[ReferencedDocument] = []

    for part in message.parts:
        if isinstance(part, UserPromptPart):
            if content := _user_prompt_content(part.content):
                items.append(
                    MessageTurnItem(
                        id=new_id("message"),
                        role="user",
                        content=content,
                    )
                )
        elif isinstance(part, ToolReturnPart):
            tool_item, cited_documents = _tool_result_item(part)
            items.append(tool_item)
            documents.extend(cited_documents)
    return items, documents


def _items_from_response(
    message: ModelResponse,
) -> tuple[list[TurnItem], list[ReferencedDocument]]:
    """Convert assistant text, images, reasoning, and tool activity on a response.

    Args:
        message: Response message from the agent run.

    Returns:
        Turn items and citations found on this response.

    """
    items: list[TurnItem] = []
    documents: list[ReferencedDocument] = []

    for part in message.parts:
        if isinstance(part, TextPart):
            items.append(
                MessageTurnItem(
                    id=new_id("message"),
                    role="assistant",
                    content=[TextContentPart(text=part.content)],
                )
            )
        elif isinstance(part, ThinkingPart):
            items.append(
                ReasoningTurnItem(
                    id=part.id or new_id("reasoning"),
                    content=part.content,
                )
            )
        elif isinstance(part, ToolCallPart):
            items.append(_tool_call_item(part))
        elif isinstance(part, ToolReturnPart):
            tool_item, cited_documents = _tool_result_item(part)
            items.append(tool_item)
            documents.extend(cited_documents)
        elif isinstance(part, FilePart) and part.content.is_image:
            items.append(
                MessageTurnItem(
                    id=new_id("message"),
                    role="assistant",
                    content=[
                        ImageContentPart(
                            image_url=AnyUrl(part.content.data_uri),
                            media_type=part.content.media_type,
                        )
                    ],
                )
            )

    return items, documents


def _tool_call_item(part: ToolCallPart) -> ToolCallTurnItem:
    """Map a function tool call to a display item.

    Args:
        part: Tool call part from the agent run.

    Returns:
        Display item for the tool call.

    """
    name, toolset = _classify_tool(part.tool_name)
    return ToolCallTurnItem(
        id=new_id("tool_call"),
        call_id=part.tool_call_id,
        name=name,
        arguments=part.args_as_dict(),
        toolset=toolset,
    )


def _tool_result_item(
    part: ToolReturnPart,
) -> tuple[ToolResultTurnItem, list[ReferencedDocument]]:
    """Map a function tool return to a display item and citations.

    Args:
        part: Tool return part from the agent run.

    Returns:
        Display item for the tool return, plus citations from search_knowledge.

    """
    name, toolset = _classify_tool(part.tool_name)
    result = ToolResultTurnItem(
        id=new_id("tool_result"),
        call_id=part.tool_call_id,
        name=name,
        status=part.outcome,
        content=_tool_result_body(part.content, fallback=part.model_response_str()),
        toolset=toolset,
    )
    if part.tool_name != _KNOWLEDGE_TOOL_NAME:
        return result, []
    return result, _knowledge_citations(part)


def _classify_tool(tool_name: str) -> tuple[str, ToolsetInfo]:
    """Return the display name and tool family for a function tool.

    Skills and search_knowledge match exact names. Local MCP tools use the
    mcp_ prefix. Any other name is a generic function tool.

    Args:
        tool_name: Tool name recorded on the agent run.

    Returns:
        Display name and tool family for the UI.

    """
    if tool_name == _KNOWLEDGE_TOOL_NAME:
        return tool_name, ToolsetInfo(type="file_search")
    if tool_name in _SKILLS_TOOL_NAMES:
        return tool_name, ToolsetInfo(type="skills")
    if tool_name.startswith(_MCP_NAME_PREFIX):
        display_name = tool_name.removeprefix(_MCP_NAME_PREFIX)
        return display_name, ToolsetInfo(type="mcp")
    return tool_name, ToolsetInfo(type="function")


def _knowledge_citations(
    part: ToolReturnPart,
) -> list[ReferencedDocument]:
    """Collect unique citations from a search_knowledge return.

    Args:
        part: Tool return whose content is a list of knowledge matches.

    Returns:
        Deduplicated citations built from match source and metadata.

    """
    documents: list[ReferencedDocument] = []
    seen_docs: set[tuple[str, str]] = set()
    for match in _knowledge_matches(part):
        if not match.content:
            continue
        document = _citation_from_match(match)
        if document is None:
            continue
        key = (str(document.doc_url or ""), document.doc_title or "")
        if key in seen_docs:
            continue
        seen_docs.add(key)
        documents.append(document)
    return documents


def _knowledge_matches(part: ToolReturnPart) -> list[KnowledgeMatch]:
    """Return knowledge matches stored on a tool return.

    Args:
        part: Tool return from an in-process search_knowledge call.

    Returns:
        Knowledge matches on the part, or an empty list.

    """
    content = part.content
    if not isinstance(content, list):
        return []
    return [item for item in content if isinstance(item, KnowledgeMatch)]


def _citation_from_match(
    match: KnowledgeMatch,
) -> Optional[ReferencedDocument]:
    """Build a citation from a knowledge match.

    Args:
        match: One search result from knowledge search.

    Returns:
        Citation when the match has a title or URL, otherwise None.

    """
    metadata = match.metadata
    title = _metadata_str(metadata, "title")
    doc_url = _url_from_match(match)
    if not title and doc_url is None:
        return None
    return ReferencedDocument(
        doc_title=title,
        doc_url=doc_url,
        source=_metadata_str(metadata, "knowledge_source"),
        document_id=_metadata_str(metadata, "document_id")
        or _metadata_str(metadata, "doc_id"),
    )


def _url_from_match(match: KnowledgeMatch) -> Optional[AnyUrl]:
    """Return a citation URL from a match source or metadata.

    Args:
        match: One search result from knowledge search.

    Returns:
        Absolute URI when one is present, otherwise None.

    """
    if parsed := _parse_url(match.source):
        return parsed
    for key in _KNOWLEDGE_URL_KEYS:
        if parsed := _parse_url(_metadata_str(match.metadata, key)):
            return parsed
    return None


def _metadata_str(metadata: Mapping[str, object], key: str) -> Optional[str]:
    """Return a non-empty string metadata value.

    Args:
        metadata: Match metadata.
        key: Metadata key to read.

    Returns:
        The string value, or None when missing or empty.

    """
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def _parse_url(value: Optional[str]) -> Optional[AnyUrl]:
    """Parse an absolute URI.

    Args:
        value: Candidate URI string.

    Returns:
        Parsed URI, or None when the value is not a URL.

    """
    if not value:
        return None
    try:
        return AnyUrl(value)
    except ValidationError:
        return None


def _tool_result_body(content: ToolReturnContent, fallback: str = "") -> ToolResultBody:
    """Serialize a tool return for display.

    Args:
        content: Tool return: a string, a dict, or a list of knowledge matches.
        fallback: Text used when content is none of those shapes.

    Returns:
        Display body for the tool result item.

    """
    if isinstance(content, str | dict):
        return content
    if isinstance(content, list):
        return [asdict(match) for match in content if isinstance(match, KnowledgeMatch)]
    return fallback


def _user_prompt_content(
    content: str | Sequence[UserContent],
) -> MessageContent:
    """Project a user prompt into display content.

    Args:
        content: User prompt text or content parts.

    Returns:
        Display content parts. Non-image binary is omitted.

    """
    if isinstance(content, str):
        return [TextContentPart(text=content)] if content else []
    parts: list[MessageContentPart] = []
    for item in content:
        converted = _user_content_part(item)
        if converted is not None:
            parts.append(converted)
    return parts


def _user_content_part(  # pylint: disable=too-many-return-statements
    item: UserContent,
) -> Optional[MessageContentPart]:
    """Map one user-content value onto a display content part.

    Args:
        item: One value from a user prompt.

    Returns:
        Display part, or None for empty text and unsupported values.

    """
    if isinstance(item, str):
        return TextContentPart(text=item) if item else None
    if isinstance(item, TextContent):
        return TextContentPart(text=item.content) if item.content else None
    if isinstance(item, ImageUrl):
        return ImageContentPart(image_url=AnyUrl(item.url), media_type=item.media_type)
    if isinstance(item, BinaryContent) and item.is_image:
        return ImageContentPart(
            image_url=AnyUrl(item.data_uri), media_type=item.media_type
        )
    if isinstance(item, DocumentUrl):
        return FileContentPart(filename=_filename_from_url(item.url))
    if isinstance(item, UploadedFile):
        if item.media_type.startswith(_IMAGE_MEDIA_PREFIX):
            return ImageContentPart(file_id=item.file_id, media_type=item.media_type)
        return FileContentPart(file_id=item.file_id)
    return None


def _filename_from_url(url: str) -> str:
    """Use the URL path basename, or the raw URL, as a file label.

    Args:
        url: Document URL from the user prompt.

    Returns:
        File name shown in the display history.

    """
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1] if path else ""
    return name or url

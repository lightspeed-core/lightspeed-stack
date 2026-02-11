"""Utilities for conversations."""

import json
from datetime import UTC, datetime
from typing import Any, Optional, Union, cast

from llama_stack_api.openai_responses import (
    OpenAIResponseOutputMessageFileSearchToolCall as FileSearchCall,
    OpenAIResponseOutputMessageFunctionToolCall as FunctionCall,
    OpenAIResponseOutputMessageMCPCall as MCPCall,
    OpenAIResponseOutputMessageMCPListTools as MCPListTools,
    OpenAIResponseOutputMessageWebSearchToolCall as WebSearchCall,
)
from llama_stack_client.types.conversations.item_list_response import (
    ItemListResponse,
    OpenAIResponseInputFunctionToolCallOutput as FunctionToolCallOutput,
    OpenAIResponseMcpApprovalRequest as MCPApprovalRequest,
    OpenAIResponseMcpApprovalResponse as MCPApprovalResponse,
    OpenAIResponseMessageOutput as MessageOutput,
)

from constants import DEFAULT_RAG_TOOL
from models.database.conversations import UserTurn
from models.responses import ConversationTurn, Message
from utils.responses import parse_arguments_string
from utils.types import ToolCallSummary, ToolResultSummary


def _extract_text_from_content(content: Union[str, list[Any]]) -> str:
    """Extract text content from message content.

    Args:
        content: The content field from a message (can be str or list)

    Returns:
        Extracted text content as a string
    """
    if isinstance(content, str):
        return content

    text_fragments: list[str] = []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                text_fragments.append(part)
                continue
            text_value = getattr(part, "text", None)
            if text_value:
                text_fragments.append(text_value)
                continue
            refusal = getattr(part, "refusal", None)
            if refusal:
                text_fragments.append(refusal)
                continue
            if isinstance(part, dict):
                dict_text = part.get("text") or part.get("refusal")
                if dict_text:
                    text_fragments.append(str(dict_text))

    return "".join(text_fragments)


def _parse_message_item(item: MessageOutput) -> Message:
    """Parse a message item into a Message object.

    Args:
        item: The message item from Conversations API

    Returns:
        Message object with extracted content and type (user or assistant)
    """
    content_text = _extract_text_from_content(item.content)
    message_type = item.role
    return Message(content=content_text, type=message_type)


def _build_tool_call_summary_from_item(  # pylint: disable=too-many-return-statements
    item: ItemListResponse,
) -> tuple[Optional[ToolCallSummary], Optional[ToolResultSummary]]:
    """Translate Conversations API tool items into ToolCallSummary and ToolResultSummary records.

    Args:
        item: A tool item from the Conversations API items list

    Returns:
        A tuple of (ToolCallSummary, ToolResultSummary) one of them possibly None
        if the item type doesn't provide both call and result information.
    """
    item_type = getattr(item, "type", None)

    if item_type == "function_call":
        function_call_item = cast(FunctionCall, item)
        return (
            ToolCallSummary(
                id=function_call_item.call_id,
                name=function_call_item.name,
                args=parse_arguments_string(function_call_item.arguments),
                type="function_call",
            ),
            None,  # Function call results come as separate function_call_output items
        )

    if item_type == "file_search_call":
        file_search_item = cast(FileSearchCall, item)
        response_payload: Optional[dict[str, Any]] = None
        if file_search_item.results is not None:
            response_payload = {
                "results": [result.model_dump() for result in file_search_item.results]
            }
        return (
            ToolCallSummary(
                id=file_search_item.id,
                name=DEFAULT_RAG_TOOL,
                args={"queries": file_search_item.queries},
                type="file_search_call",
            ),
            ToolResultSummary(
                id=file_search_item.id,
                status=file_search_item.status,
                content=json.dumps(response_payload) if response_payload else "",
                type="file_search_call",
                round=1,
            ),
        )

    if item_type == "web_search_call":
        web_search_item = cast(WebSearchCall, item)
        return (
            ToolCallSummary(
                id=web_search_item.id,
                name="web_search",
                args={},
                type="web_search_call",
            ),
            ToolResultSummary(
                id=web_search_item.id,
                status=web_search_item.status,
                content="",
                type="web_search_call",
                round=1,
            ),
        )

    if item_type == "mcp_call":
        mcp_call_item = cast(MCPCall, item)
        args = parse_arguments_string(mcp_call_item.arguments)
        if mcp_call_item.server_label:
            args["server_label"] = mcp_call_item.server_label
        content = (
            mcp_call_item.error
            if mcp_call_item.error
            else (mcp_call_item.output if mcp_call_item.output else "")
        )

        return (
            ToolCallSummary(
                id=mcp_call_item.id,
                name=mcp_call_item.name,
                args=args,
                type="mcp_call",
            ),
            ToolResultSummary(
                id=mcp_call_item.id,
                status="success" if mcp_call_item.error is None else "failure",
                content=content,
                type="mcp_call",
                round=1,
            ),
        )

    if item_type == "mcp_list_tools":
        mcp_list_tools_item = cast(MCPListTools, item)
        tools_info = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in mcp_list_tools_item.tools
        ]
        content_dict = {
            "server_label": mcp_list_tools_item.server_label,
            "tools": tools_info,
        }
        return (
            ToolCallSummary(
                id=mcp_list_tools_item.id,
                name="mcp_list_tools",
                args={"server_label": mcp_list_tools_item.server_label},
                type="mcp_list_tools",
            ),
            ToolResultSummary(
                id=mcp_list_tools_item.id,
                status="success",
                content=json.dumps(content_dict),
                type="mcp_list_tools",
                round=1,
            ),
        )

    if item_type == "mcp_approval_request":
        approval_request_item = cast(MCPApprovalRequest, item)
        args = parse_arguments_string(approval_request_item.arguments)
        return (
            ToolCallSummary(
                id=approval_request_item.id,
                name=approval_request_item.name,
                args=args,
                type="tool_call",
            ),
            None,
        )

    if item_type == "mcp_approval_response":
        approval_response_item = cast(MCPApprovalResponse, item)
        content_dict = {}
        if approval_response_item.reason:
            content_dict["reason"] = approval_response_item.reason
        return (
            None,
            ToolResultSummary(
                id=approval_response_item.approval_request_id,
                status="success" if approval_response_item.approve else "denied",
                content=json.dumps(content_dict),
                type="mcp_approval_response",
                round=1,
            ),
        )

    if item_type == "function_call_output":
        function_output = cast(FunctionToolCallOutput, item)
        return (
            None,
            ToolResultSummary(
                id=function_output.call_id,
                status=function_output.status or "success",
                content=function_output.output,
                type="function_call_output",
                round=1,
            ),
        )

    return None, None


def _create_dummy_turn_metadata(started_at: datetime) -> UserTurn:
    """Create a dummy UserTurn instance for legacy conversations without metadata.

    Args:
        started_at: Timestamp to use for started_at and completed_at (conversation created_at)

    Returns:
        UserTurn instance with default values (N/A for provider/model, provided timestamp)
        for legacy conversations that don't have stored turn metadata.
    """
    # Create a UserTurn instance with default values for legacy conversations
    # Note: conversation_id and turn_number are not used, so we use placeholder values
    return UserTurn(
        conversation_id="",
        turn_number=0,
        started_at=started_at,
        completed_at=started_at,
        provider="N/A",
        model="N/A",
    )


def _create_turn_from_db_metadata(
    turn_metadata: UserTurn,
    messages: list[Message],
    tool_calls: list[ToolCallSummary],
    tool_results: list[ToolResultSummary],
) -> ConversationTurn:
    """Create a ConversationTurn from database metadata and accumulated items.

    Args:
        turn_metadata: Database UserTurn object with metadata
        messages: List of messages for this turn
        tool_calls: List of tool calls for this turn
        tool_results: List of tool results for this turn

    Returns:
        ConversationTurn object with all metadata populated
    """
    started_at = turn_metadata.started_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    completed_at = turn_metadata.completed_at.astimezone(UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return ConversationTurn(
        messages=messages,
        tool_calls=tool_calls,
        tool_results=tool_results,
        provider=turn_metadata.provider,
        model=turn_metadata.model,
        started_at=started_at,
        completed_at=completed_at,
    )


def _group_items_into_turns(
    items: list[ItemListResponse],
) -> list[list[ItemListResponse]]:
    """Group conversation items into turns.

    Each turn starts with a user message. All subsequent messages and tool items
    belong to that turn until the next user message.

    Args:
        items: Conversation items list from Conversations API, oldest first

    Returns:
        List of turns, where each turn is a list of items belonging to that turn
    """
    turns: list[list[ItemListResponse]] = []
    current_turn_items: list[ItemListResponse] = []

    for item in items:
        item_type = getattr(item, "type", None)

        # User message marks the beginning of a new turn
        if item_type == "message":
            message_item = cast(MessageOutput, item)
            if message_item.role == "user":
                # If we have accumulated items, finish the previous turn
                if current_turn_items:
                    turns.append(current_turn_items)
                    current_turn_items = []

                # Start new turn with this user message
                current_turn_items = [item]
            else:
                # Add non-user message to current turn
                current_turn_items.append(item)
        else:
            # Add tool-related items to current turn
            current_turn_items.append(item)

    # Add final turn if there are items
    if current_turn_items:
        turns.append(current_turn_items)

    return turns


def _process_turn_items(
    turn_items: list[ItemListResponse],
) -> tuple[list[Message], list[ToolCallSummary], list[ToolResultSummary]]:
    """Process items from a single turn into messages, tool calls, and tool results.

    Args:
        turn_items: List of items belonging to a single turn

    Returns:
        Tuple of (messages, tool_calls, tool_results)
    """
    messages: list[Message] = []
    tool_calls: list[ToolCallSummary] = []
    tool_results: list[ToolResultSummary] = []

    for item in turn_items:
        item_type = getattr(item, "type", None)

        if item_type == "message":
            message_item = cast(MessageOutput, item)
            message = _parse_message_item(message_item)
            messages.append(message)
        else:
            tool_call, tool_result = _build_tool_call_summary_from_item(item)
            if tool_call is not None:
                tool_calls.append(tool_call)
            if tool_result is not None:
                tool_results.append(tool_result)

    return messages, tool_calls, tool_results


def build_conversation_turns_from_items(
    items: list[ItemListResponse],
    turns_metadata: list[UserTurn],
    conversation_start_time: datetime,
) -> list[ConversationTurn]:
    """Build conversation turns from Conversations API items and turns metadata.

    Args:
        items: Conversation items list from Conversations API, oldest first
        turns_metadata: List of UserTurn database objects ordered by turn_number.
            Can be empty for legacy conversations without stored metadata.
            For extended legacy conversations, only the newer turns have metadata.
        conversation_start_time: Timestamp to use for dummy metadata in legacy conversations.
            Typically the conversation's created_at timestamp.

    Returns:
        List of ConversationTurn objects, oldest first
    """
    # Group items into turns first
    turn_items_list = _group_items_into_turns(items)

    # Calculate how many legacy turns don't have metadata
    total_turns = len(turn_items_list)
    legacy_turns_count = total_turns - len(turns_metadata)

    # Process each turn with its corresponding metadata
    chat_history: list[ConversationTurn] = []
    for turn_index, turn_items in enumerate(turn_items_list):
        # Process items into messages, tool calls, and tool results
        messages, tool_calls, tool_results = _process_turn_items(turn_items)

        # Select appropriate metadata for this turn
        if turn_index < legacy_turns_count:
            turn_metadata = _create_dummy_turn_metadata(conversation_start_time)
        else:
            metadata_index = turn_index - legacy_turns_count
            turn_metadata = turns_metadata[metadata_index]

        # Create ConversationTurn from metadata and processed items
        chat_history.append(
            _create_turn_from_db_metadata(
                turn_metadata,
                messages,
                tool_calls,
                tool_results,
            )
        )

    return chat_history

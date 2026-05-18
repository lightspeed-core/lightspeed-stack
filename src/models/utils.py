"""Utility functions for models."""

from typing import Any

from llama_stack_api.openai_responses import OpenAIResponseInputTool as InputTool


def add_mcp_authorizations(
    dumped_tools: list[dict[str, Any]],
    tools: list[InputTool],
) -> list[dict[str, Any]]:
    """Merge MCP authorization into serialized tool dicts keyed by server_label.

    Args:
        dumped_tools: Serialized tools.
        tools: Live tool models. MCP entries with authorization are mapped by
            server_label.

    Returns:
        A new list of dicts. For MCP rows, authorization is set only when a
        matching non-None token exists.
    """
    authorizations = {
        tool.server_label: tool.authorization
        for tool in tools
        if tool.type == "mcp" and tool.authorization is not None
    }  # server_labels are unique by design
    result: list[dict[str, Any]] = []
    for dumped in dumped_tools:
        row = dict(dumped)
        if (
            row.get("type") == "mcp"
            and (label := row.get("server_label")) is not None
            and (token := authorizations.get(label)) is not None
        ):
            row["authorization"] = token

        result.append(row)
    return result

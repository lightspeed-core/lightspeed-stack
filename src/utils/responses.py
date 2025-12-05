"""Utility functions for processing Responses API output."""

from typing import Any


def extract_text_from_response_output_item(output_item: Any) -> str:
    """Extract assistant message text from a Responses API output item.

    This function parses output items from the OpenAI-compatible Responses API
    and extracts text content from assistant messages. It handles multiple content
    formats including string content, content arrays with text parts, and refusal
    messages.

    Args:
        output_item: A Responses API output item (typically from response.output array).
            Expected to have attributes like type, role, and content.

    Returns:
        str: The extracted text content from the assistant message. Returns an empty
            string if the output_item is not an assistant message or contains no text.

    Example:
        >>> for output_item in response.output:
        ...     text = extract_text_from_response_output_item(output_item)
        ...     if text:
        ...         print(text)
    """
    if getattr(output_item, "type", None) != "message":
        return ""
    if getattr(output_item, "role", None) != "assistant":
        return ""

    content = getattr(output_item, "content", None)
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

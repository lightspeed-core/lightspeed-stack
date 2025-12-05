"""Unit tests for utils/responses.py functions."""

from types import SimpleNamespace
from typing import Any

import pytest

from utils.responses import extract_text_from_response_output_item


def make_output_item(
    item_type: str | None = None, role: str | None = None, content: Any = None
) -> SimpleNamespace:
    """Create a mock Responses API output item.

    Args:
        item_type: The type of the output item (e.g., "message", "function_call")
        role: The role of the message (e.g., "assistant", "user")
        content: The content of the message (can be str, list, or None)

    Returns:
        SimpleNamespace: Mock object with type, role, and content attributes
    """
    return SimpleNamespace(type=item_type, role=role, content=content)


def make_content_part(
    text: str | None = None, refusal: str | None = None
) -> SimpleNamespace:
    """Create a mock content part for message content.

    Args:
        text: Text content of the part
        refusal: Refusal message content

    Returns:
        SimpleNamespace: Mock object with text and/or refusal attributes
    """
    return SimpleNamespace(text=text, refusal=refusal)


@pytest.mark.parametrize(
    "item_type,role,content,expected",
    [
        # Non-message types should return empty string
        ("function_call", "assistant", "some text", ""),
        ("file_search_call", "assistant", "some text", ""),
        (None, "assistant", "some text", ""),
        # Non-assistant roles should return empty string
        ("message", "user", "some text", ""),
        ("message", "system", "some text", ""),
        ("message", None, "some text", ""),
        # Valid assistant message with string content
        ("message", "assistant", "Hello, world!", "Hello, world!"),
        ("message", "assistant", "", ""),
        # No content attribute
        ("message", "assistant", None, ""),
    ],
    ids=[
        "function_call_type_returns_empty",
        "file_search_call_type_returns_empty",
        "none_type_returns_empty",
        "user_role_returns_empty",
        "system_role_returns_empty",
        "none_role_returns_empty",
        "valid_string_content",
        "empty_string_content",
        "none_content",
    ],
)
def test_extract_text_basic_cases(
    item_type: str, role: str, content: Any, expected: str
) -> None:
    """Test basic extraction cases for different types, roles, and simple content.

    Args:
        item_type: Type of the output item
        role: Role of the message
        content: Content of the message
        expected: Expected extracted text
    """
    output_item = make_output_item(item_type=item_type, role=role, content=content)
    result = extract_text_from_response_output_item(output_item)
    assert result == expected


@pytest.mark.parametrize(
    "content_parts,expected",
    [
        # List with string items
        (["Hello", " ", "world"], "Hello world"),
        (["Single string"], "Single string"),
        ([], ""),
        # List with make_content_part objects containing text
        (
            [make_content_part(text="Part 1"), make_content_part(text=" Part 2")],
            "Part 1 Part 2",
        ),
        ([make_content_part(text="Only text")], "Only text"),
        # List with make_content_part objects containing refusal
        (
            [make_content_part(refusal="I cannot help with that")],
            "I cannot help with that",
        ),
        (
            [
                make_content_part(text="Some text"),
                make_content_part(refusal=" but I refuse"),
            ],
            "Some text but I refuse",
        ),
        # List with dict items
        ([{"text": "Dict text 1"}, {"text": "Dict text 2"}], "Dict text 1Dict text 2"),
        ([{"refusal": "Dict refusal"}], "Dict refusal"),
        ([{"text": "Text"}, {"refusal": "Refusal"}], "TextRefusal"),
        # Mixed content types
        (
            [
                "String part",
                make_content_part(text=" Object part"),
                {"text": " Dict part"},
            ],
            "String part Object part Dict part",
        ),
        (
            [
                make_content_part(text="Text"),
                make_content_part(refusal=" Refusal"),
                {"text": " DictText"},
                " String",
            ],
            "Text Refusal DictText String",
        ),
        # Content parts with None or missing attributes
        ([make_content_part(text=None), make_content_part(refusal=None)], ""),
        ([{"other_key": "value"}], ""),
        ([make_content_part(text="Valid"), {"invalid": "key"}], "Valid"),
    ],
    ids=[
        "list_of_strings",
        "list_single_string",
        "empty_list",
        "list_of_objects_with_text",
        "single_object_with_text",
        "object_with_refusal",
        "mixed_text_and_refusal_objects",
        "list_of_dicts_with_text",
        "dict_with_refusal",
        "dict_mixed_text_refusal",
        "mixed_string_object_dict",
        "complex_mixed_content",
        "none_attributes",
        "dict_without_text_or_refusal",
        "valid_mixed_with_invalid",
    ],
)
def test_extract_text_list_content(content_parts: list[Any], expected: str) -> None:
    """Test extraction from list-based content with various part types.

    Args:
        content_parts: List of content parts (strings, objects, dicts)
        expected: Expected concatenated text result
    """
    output_item = make_output_item(
        item_type="message", role="assistant", content=content_parts
    )
    result = extract_text_from_response_output_item(output_item)
    assert result == expected


def test_extract_text_with_real_world_structure() -> None:
    """Test extraction with a structure mimicking real Responses API output.

    This test simulates a typical response structure with multiple content parts
    including text and potential refusals.
    """
    # Simulate a real-world response with multiple content parts
    content = [
        make_content_part(text="I can help you with that. "),
        make_content_part(text="Here's the information you requested: "),
        "The answer is 42.",
    ]

    output_item = make_output_item(
        item_type="message", role="assistant", content=content
    )
    result = extract_text_from_response_output_item(output_item)

    expected = "I can help you with that. Here's the information you requested: The answer is 42."
    assert result == expected


def test_extract_text_with_numeric_dict_values() -> None:
    """Test that numeric values in dicts are properly converted to strings.

    Ensures that when dict values are numeric, they're converted to strings
    during extraction.
    """
    content = [{"text": 123}, {"refusal": 456}]

    output_item = make_output_item(
        item_type="message", role="assistant", content=content
    )
    result = extract_text_from_response_output_item(output_item)

    # Numbers should be converted to strings
    assert result == "123456"


def test_extract_text_preserves_order() -> None:
    """Test that content parts are concatenated in the correct order.

    Verifies that the order of content parts is preserved during extraction.
    """
    content = [
        "First",
        make_content_part(text=" Second"),
        {"text": " Third"},
        " Fourth",
    ]

    output_item = make_output_item(
        item_type="message", role="assistant", content=content
    )
    result = extract_text_from_response_output_item(output_item)

    assert result == "First Second Third Fourth"


@pytest.mark.parametrize(
    "missing_attr",
    ["type", "role", "content"],
    ids=["missing_type", "missing_role", "missing_content"],
)
def test_extract_text_handles_missing_attributes(missing_attr: str) -> None:
    """Test graceful handling when expected attributes are missing.

    Args:
        missing_attr: The attribute to omit from the mock object
    """

    # Create a basic dict-like object without using make_output_item
    # pylint: disable=too-few-public-methods,missing-class-docstring,attribute-defined-outside-init
    class PartialMock:
        pass

    output_item = PartialMock()

    # Add only the attributes we want
    if missing_attr != "type":
        output_item.type = "message"  # type: ignore
    if missing_attr != "role":
        output_item.role = "assistant"  # type: ignore
    if missing_attr != "content":
        output_item.content = "Some text"  # type: ignore

    result = extract_text_from_response_output_item(output_item)

    # Should return empty string when critical attributes are missing
    assert result == ""

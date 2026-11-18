"""Tests for display-history message content parts."""

import pytest
from pydantic import AnyUrl, ValidationError

from conversations.display_history.agentic.models.content import (
    FileContentPart,
    ImageContentPart,
    TextContentPart,
    message_content_to_text,
)
from conversations.display_history.agentic.models.turn_items import MessageTurnItem


def test_message_content_to_text_concatenates_text_parts() -> None:
    """Only text parts contribute to the concatenated message string."""
    content = [
        TextContentPart(text="Describe this:"),
        ImageContentPart(image_url=AnyUrl("https://example.com/a.png")),
        ImageContentPart(file_id="file_abc123"),
    ]
    item = MessageTurnItem(id="u1", role="user", content=content)
    assert message_content_to_text(item.content) == "Describe this:"


def test_message_rejects_plain_string_content() -> None:
    """Message content must be a list of parts, not a bare string."""
    with pytest.raises(ValidationError):
        MessageTurnItem(
            id="u1",
            role="user",
            content="Hello",  # type: ignore[arg-type]
        )


def test_image_part_requires_url_or_file_id() -> None:
    """An image must have a URL, a file id, or both."""
    assert ImageContentPart(
        image_url=AnyUrl("https://example.com/a.png")
    ).image_url == AnyUrl("https://example.com/a.png")
    assert ImageContentPart(file_id="file_abc123").file_id == "file_abc123"
    with pytest.raises(ValidationError):
        ImageContentPart()


def test_image_part_accepts_media_type() -> None:
    """Media type is optional metadata on an image part."""
    part = ImageContentPart(
        image_url=AnyUrl("https://example.com/a.png"),
        media_type="image/png",
    )
    assert part.media_type == "image/png"
    assert ImageContentPart(file_id="file_abc123").media_type is None


def test_file_part_requires_id_or_filename() -> None:
    """A file must have an upload id, a filename, or both."""
    assert FileContentPart(file_id="file_xyz").file_id == "file_xyz"
    assert FileContentPart(filename="notes.pdf").filename == "notes.pdf"
    with pytest.raises(ValidationError):
        FileContentPart()

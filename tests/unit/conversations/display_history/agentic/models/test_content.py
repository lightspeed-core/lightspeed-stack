"""Tests for conversations.display_history.agentic.models.content."""

import pytest
from pydantic import AnyUrl, ValidationError

from conversations.display_history.agentic.models.content import (
    ImageContentPart,
    TextContentPart,
    message_content_to_text,
)
from conversations.display_history.agentic.models.turn_items import MessageTurnItem


class TestMessageContent:
    """Multimodal message parts."""

    def test_multimodal_message_and_image_reference(self) -> None:
        """Message content is part-based; images use URL or file_id."""
        content = [
            TextContentPart(text="Describe this:"),
            ImageContentPart(image_url=AnyUrl("https://example.com/a.png")),
            ImageContentPart(file_id="file_abc123"),
        ]
        item = MessageTurnItem(id="u1", role="user", content=content)
        assert message_content_to_text(item.content) == "Describe this:"

        with pytest.raises(ValidationError):
            MessageTurnItem(
                id="u1",
                role="user",
                content="Hello",  # type: ignore[arg-type]
            )

"""Multimodal message content parts for user and assistant turn items."""

from typing import Annotated, Literal, Optional, Self

from pydantic import AnyUrl, BaseModel, Field, model_validator


class TextContentPart(BaseModel):
    """Text segment within a multimodal message."""

    type: Literal["text"] = "text"
    text: str = Field(..., description="Message text")


class ImageContentPart(BaseModel):
    """Image reference for display (not raw bytes).

    Matches how clients render history: a URL and/or an uploaded file_id.
    Inference-only fields such as vision detail are not stored in display history.
    """

    type: Literal["image"] = "image"
    image_url: Optional[AnyUrl] = Field(
        default=None,
        description="URL of the image when the client supplied a link",
    )
    file_id: Optional[str] = Field(
        default=None,
        description="Uploaded file identifier when the image is stored by LCORE",
    )

    @model_validator(mode="after")
    def validate_image_reference(self) -> Self:
        """Require at least one resolvable image reference."""
        if self.image_url is None and not self.file_id:
            raise ValueError("image_url or file_id is required")
        return self


class FileContentPart(BaseModel):
    """File reference within a multimodal message."""

    type: Literal["file"] = "file"
    file_id: Optional[str] = Field(
        default=None,
        description="Uploaded file identifier",
    )
    filename: Optional[str] = Field(
        default=None,
        description="Original filename when available",
    )


MessageContentPart = Annotated[
    TextContentPart | ImageContentPart | FileContentPart,
    Field(discriminator="type"),
]

type MessageContent = list[MessageContentPart]
"""Ordered multimodal parts for user or assistant message items."""


def text_message_content(text: str) -> MessageContent:
    """Build single-part text content for mappers and tests."""
    return [TextContentPart(text=text)]


def message_content_to_text(content: MessageContent) -> str:
    """Return concatenated text from all TextContentPart entries."""
    return "".join(part.text for part in content if isinstance(part, TextContentPart))

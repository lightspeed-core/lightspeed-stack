"""Unit tests for Attachment model."""

import base64

import pytest
from pydantic import ValidationError

from models.common.query import Attachment


class TestAttachment:
    """Test cases for the Attachment model."""

    def test_constructor(self) -> None:
        """Test the Attachment with custom values."""
        a = Attachment(
            attachment_type="configuration",
            content_type="application/yaml",
            content="kind: Pod\n metadata:\n name:    private-reg",
        )
        assert a.attachment_type == "configuration"
        assert a.content_type == "application/yaml"
        assert a.content == "kind: Pod\n metadata:\n name:    private-reg"

    def test_constructor_unknown_attachment_type(self) -> None:
        """Test the Attachment with custom values.

        Verify that an Attachment retains the provided attachment_type,
        content_type, and content when given an unrecognized content type.

        Asserts that `attachment_type` is "configuration", `content_type` is
        "unknown/type", and `content` matches the supplied multi-line YAML
        string.
        """
        # for now we allow any content type
        a = Attachment(
            attachment_type="configuration",
            content_type="unknown/type",
            content="kind: Pod\n metadata:\n name:    private-reg",
        )
        assert a.attachment_type == "configuration"
        assert a.content_type == "unknown/type"
        assert a.content == "kind: Pod\n metadata:\n name:    private-reg"

    def test_valid_image_attachment_jpeg(self) -> None:
        """Test that a valid JPEG image attachment is accepted."""
        image_data = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 100).decode()
        a = Attachment(
            attachment_type="image",
            content_type="image/jpeg",
            content=image_data,
        )
        assert a.attachment_type == "image"
        assert a.content_type == "image/jpeg"

    def test_valid_image_attachment_png(self) -> None:
        """Test that a valid PNG image attachment is accepted."""
        image_data = base64.b64encode(b"\x89PNG" + b"\x00" * 100).decode()
        a = Attachment(
            attachment_type="image",
            content_type="image/png",
            content=image_data,
        )
        assert a.attachment_type == "image"
        assert a.content_type == "image/png"

    def test_image_content_type_requires_image_attachment_type(self) -> None:
        """Test that image content_type requires attachment_type='image'."""
        image_data = base64.b64encode(b"\xff\xd8\xff\xe0").decode()
        with pytest.raises(ValidationError, match="attachment_type must be 'image'"):
            Attachment(
                attachment_type="log",
                content_type="image/jpeg",
                content=image_data,
            )

    def test_image_attachment_type_requires_image_content_type(self) -> None:
        """Test that attachment_type='image' requires an image content_type."""
        with pytest.raises(
            ValidationError, match="content_type must be 'image/jpeg' or 'image/png'"
        ):
            Attachment(
                attachment_type="image",
                content_type="text/plain",
                content="some text",
            )

    def test_image_attachment_invalid_base64(self) -> None:
        """Test that image attachment with invalid base64 is rejected."""
        with pytest.raises(ValidationError, match="Invalid base64"):
            Attachment(
                attachment_type="image",
                content_type="image/jpeg",
                content="not-valid-base64!!!",
            )

    def test_image_attachment_exceeds_size_limit(self) -> None:
        """Test that image attachment exceeding size limit is rejected."""
        large_data = base64.b64encode(b"\x00" * (100 * 1024 * 1024 + 1)).decode()
        with pytest.raises(ValidationError, match="exceeds maximum allowed size"):
            Attachment(
                attachment_type="image",
                content_type="image/png",
                content=large_data,
            )

    def test_text_attachment_unchanged(self) -> None:
        """Test that existing text attachments still work without changes."""
        a = Attachment(
            attachment_type="log",
            content_type="text/plain",
            content="some log output",
        )
        assert a.attachment_type == "log"
        assert a.content_type == "text/plain"

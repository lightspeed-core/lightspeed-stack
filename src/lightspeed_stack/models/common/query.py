"""Shared query-related request primitives."""

import base64
import binascii
from typing import Any, Literal, Optional, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from constants import (
    DEFAULT_MAX_FILE_UPLOAD_SIZE,
    IMAGE_CONTENT_TYPES,
    SOLR_VECTOR_SEARCH_DEFAULT_MODE,
)
from log import get_logger

logger = get_logger(__name__)

_IMAGE_SIGNATURES: dict[str, bytes] = {
    "image/png": b"\x89PNG",
    "image/jpeg": b"\xff\xd8\xff",
}


def _validate_image_magic_bytes(data: bytes, content_type: str) -> None:
    """Verify that decoded image data starts with the expected magic bytes.

    Parameters:
        data: Raw decoded image bytes.
        content_type: Declared MIME content type.

    Raises:
        ValueError: If the data does not match the expected image format.
    """
    expected = _IMAGE_SIGNATURES.get(content_type)
    if expected and not data.startswith(expected):
        raise ValueError(
            f"Image content does not match declared content_type "
            f"'{content_type}': invalid image data"
        )


class Attachment(BaseModel):
    """Model representing an attachment that can be sent from the UI as part of query.

    A list of attachments can be an optional part of 'query' request.

    Attributes:
        attachment_type: The attachment type, like "log", "configuration", "image" etc.
        content_type: The content type as defined in MIME standard
        content: The actual attachment content (text or base64-encoded image data)
    """

    attachment_type: str = Field(
        description="The attachment type, like 'log', 'configuration', 'image' etc.",
        examples=["log", "image"],
    )
    content_type: str = Field(
        description="The content type as defined in MIME standard",
        examples=["text/plain", "image/jpeg", "image/png"],
    )
    content: str = Field(
        description="The actual attachment content (text or base64-encoded image data)",
        examples=["warning: quota exceeded"],
    )

    @model_validator(mode="after")
    def validate_image_attachment(self) -> Self:
        """Validate consistency between attachment_type and content_type for images.

        Returns:
            Self: The validated Attachment instance.

        Raises:
            ValueError: If attachment_type and content_type are inconsistent
                (one indicates an image while the other does not),
                if image content is not valid base64, or if decoded size exceeds the limit.
        """
        is_image_content_type = self.content_type in IMAGE_CONTENT_TYPES
        is_image_attachment_type = self.attachment_type == "image"

        if is_image_content_type != is_image_attachment_type:
            raise ValueError(
                f"attachment_type and content_type are inconsistent: "
                f"attachment_type='{self.attachment_type}', "
                f"content_type='{self.content_type}'"
            )

        if is_image_content_type:
            try:
                decoded = base64.b64decode(self.content, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError(
                    f"Invalid base64 content for image attachment: {exc}"
                ) from exc
            if len(decoded) > DEFAULT_MAX_FILE_UPLOAD_SIZE:
                raise ValueError(
                    f"Image attachment ({len(decoded)} bytes) exceeds maximum "
                    f"allowed size ({DEFAULT_MAX_FILE_UPLOAD_SIZE} bytes)"
                )
            _validate_image_magic_bytes(decoded, self.content_type)

        return self

    # provides examples for /docs endpoint
    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "attachment_type": "log",
                    "content_type": "text/plain",
                    "content": "this is attachment",
                },
                {
                    "attachment_type": "configuration",
                    "content_type": "application/yaml",
                    "content": "kind: Pod\n metadata:\n name:    private-reg",
                },
                {
                    "attachment_type": "configuration",
                    "content_type": "application/yaml",
                    "content": "foo: bar",
                },
                {
                    "attachment_type": "image",
                    "content_type": "image/png",
                    "content": "<base64-encoded image data>",
                },
            ]
        },
    }


class SolrVectorSearchRequest(BaseModel):
    """LCORE Solr inline RAG options for vector_io.query (mode and provider filters).

    Attributes:
        mode: Solr vector_io search mode. When omitted, the server default (hybrid) is used.
        filters: Solr provider filter payload passed through as params['solr'].

    Legacy clients may send a plain JSON object with filter keys only;
    that object is accepted as filters with mode unset (server default applies).
    """

    model_config = ConfigDict(extra="forbid")

    mode: Optional[Literal["semantic", "hybrid", "lexical"]] = Field(
        None,
        description=(
            "Solr vector_io search mode. When omitted, the server default "
            f"({SOLR_VECTOR_SEARCH_DEFAULT_MODE!r}) is used."
        ),
        examples=["hybrid", "semantic", "lexical"],
    )
    filters: Optional[dict[str, Any]] = Field(
        None,
        description=(
            "Solr provider filter payload passed through as params['solr']. "
            "Supports structured metadata filters (eq, ne, in, nin comparison operators). "
            "Legacy filter-only objects (e.g. fq) are still accepted."
        ),
        examples=[
            {
                "filters": {
                    "type": "eq",
                    "key": "product",
                    "value": "openshift_container_platform",
                }
            },
            {
                "filters": {
                    "type": "and",
                    "filters": [
                        {
                            "type": "eq",
                            "key": "product",
                            "value": "openshift_container_platform",
                        },
                        {
                            "type": "in",
                            "key": "version",
                            "value": ["4.14", "4.15", "4.16"],
                        },
                    ],
                }
            },
            {"fq": ["product:*openshift*"]},
        ],
    )

    @model_validator(mode="before")
    @classmethod
    def coerce_legacy_plain_dict(cls, data: Any) -> Any:
        """Treat a legacy top-level filter dict as filters (backward compatibility).

        Args:
            data: Raw JSON, typically a dict or None.

        Returns:
            Normalized dict for Pydantic model validation, or the original non-dict value.
        """
        if data is None or not isinstance(data, dict):
            return data
        if "filters" in data or "mode" in data:
            return data
        logger.warning(
            "Solr inline RAG: sending filter fields at the top level of `solr` without "
            "`mode` or `filters` is deprecated and will be removed; use "
            '`{"mode": "<semantic|hybrid|lexical>", "filters": {...}}` instead.'
        )
        return {"mode": None, "filters": data}

"""Shared query-related request primitives."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from constants import SOLR_VECTOR_SEARCH_DEFAULT_MODE
from log import get_logger

logger = get_logger(__name__)


class Attachment(BaseModel):
    """Model representing an attachment that can be sent from the UI as part of query.

    A list of attachments can be an optional part of 'query' request.

    Attributes:
        attachment_type: The attachment type, like "log", "configuration" etc.
        content_type: The content type as defined in MIME standard
        content: The actual attachment content
    """

    attachment_type: str = Field(
        description="The attachment type, like 'log', 'configuration' etc.",
        examples=["log"],
    )
    content_type: str = Field(
        description="The content type as defined in MIME standard",
        examples=["text/plain"],
    )
    content: str = Field(
        description="The actual attachment content",
        examples=["warning: quota exceeded"],
    )

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

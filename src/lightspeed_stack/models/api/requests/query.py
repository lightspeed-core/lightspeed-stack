"""Request models for query and streaming interrupt endpoints."""

from typing import Optional, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from constants import MEDIA_TYPE_JSON, MEDIA_TYPE_TEXT
from models.common.query import Attachment, SolrVectorSearchRequest
from utils import suid


class QueryRequest(BaseModel):
    """Model representing a request for the LLM (Language Model).

    Attributes:
        query: The query string.
        conversation_id: The optional conversation ID (UUID).
        provider: The optional provider.
        model: The optional model.
        system_prompt: The optional system prompt.
        attachments: The optional attachments.
        no_tools: Whether to bypass all tools and MCP servers (default: False).
        generate_topic_summary: Whether to generate topic summary for new conversations.
        media_type: The optional media type for response format (application/json or text/plain).
        vector_store_ids: The optional list of specific vector store IDs to query for RAG.
        shield_ids: The optional list of safety shield IDs to apply.
        solr: Optional Solr inline RAG options (mode, filters) or legacy filter-only dict.
    """

    query: str = Field(
        description="The query string",
        examples=["What is Kubernetes?"],
    )

    conversation_id: Optional[str] = Field(
        None,
        description="The optional conversation ID (UUID)",
        examples=["c5260aec-4d82-4370-9fdf-05cf908b3f16"],
    )

    provider: Optional[str] = Field(
        None,
        description="The optional provider",
        examples=["openai", "watsonx"],
    )

    model: Optional[str] = Field(
        None,
        description="The optional model",
        examples=["gpt4mini"],
    )

    system_prompt: Optional[str] = Field(
        None,
        description="The optional system prompt.",
        examples=["You are OpenShift assistant.", "You are Ansible assistant."],
    )

    attachments: Optional[list[Attachment]] = Field(
        None,
        description="The optional list of attachments.",
        examples=[
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
        ],
    )

    no_tools: Optional[bool] = Field(
        False,
        description="Whether to bypass all tools and MCP servers",
        examples=[True, False],
    )

    generate_topic_summary: Optional[bool] = Field(
        True,
        description="Whether to generate topic summary for new conversations",
        examples=[True, False],
    )

    media_type: Optional[str] = Field(
        None,
        description="Media type for the response format",
        examples=[MEDIA_TYPE_JSON, MEDIA_TYPE_TEXT],
    )

    vector_store_ids: Optional[list[str]] = Field(
        None,
        description="Optional list of specific vector store IDs to query for RAG. "
        "If not provided, all available vector stores will be queried.",
        examples=["ocp_docs", "knowledge_base", "vector_db_1"],
    )

    shield_ids: Optional[list[str]] = Field(
        None,
        description="Optional list of safety shield IDs to apply. "
        "If None, all configured shields are used. ",
        examples=["llama-guard", "custom-shield"],
    )

    solr: Optional[SolrVectorSearchRequest] = Field(
        None,
        description=(
            "Solr inline RAG config: mode (semantic, hybrid, lexical) and filters; "
            "a legacy filter-only object (e.g. fq) is still accepted."
        ),
        examples=[
            {"mode": "hybrid", "filters": {"fq": ["product:*openshift*"]}},
            {"filters": {"fq": ["product:*openshift*", "product_version:*4.16*"]}},
        ],
    )

    # provides examples for /docs endpoint
    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {
                    "query": "write a deployment yaml for the mongodb image",
                    "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                    "provider": "openai",
                    "model": "model-name",
                    "system_prompt": "You are a helpful assistant",
                    "no_tools": False,
                    "generate_topic_summary": True,
                    "vector_store_ids": ["ocp_docs", "knowledge_base"],
                    "attachments": [
                        {
                            "attachment_type": "log",
                            "content_type": "text/plain",
                            "content": "this is attachment",
                        },
                        {
                            "attachment_type": "configuration",
                            "content_type": "application/yaml",
                            "content": "kind: Pod\n metadata:\n    name: private-reg",
                        },
                        {
                            "attachment_type": "configuration",
                            "content_type": "application/yaml",
                            "content": "foo: bar",
                        },
                    ],
                }
            ]
        },
    }

    @field_validator("conversation_id")
    @classmethod
    def check_uuid(cls, value: Optional[str]) -> Optional[str]:
        """Validate that a conversation identifier matches the expected SUID format.

        Args:
            value: Conversation identifier to validate; may be None.

        Returns:
            The original value if valid or None if not provided.

        Raises:
            ValueError: If value is provided and does not conform to the
                expected SUID format.
        """
        if value and not suid.check_suid(value):
            raise ValueError(f"Improper conversation ID '{value}'")
        return value

    @model_validator(mode="after")
    def validate_provider_and_model(self) -> Self:
        """Ensure provider and model are specified together.

        Returns:
            The validated model instance.

        Raises:
            ValueError: If only provider or only model is provided (they must be set together).
        """
        if self.model and not self.provider:
            raise ValueError("Provider must be specified if model is specified")
        if self.provider and not self.model:
            raise ValueError("Model must be specified if provider is specified")
        return self

    @model_validator(mode="after")
    def validate_media_type(self) -> Self:
        """Ensure the media_type field, if present, is one of the allowed response media types.

        Returns:
            The model instance when validation passes.

        Raises:
            ValueError: If media_type is not equal to MEDIA_TYPE_JSON or MEDIA_TYPE_TEXT.
        """
        if self.media_type and self.media_type not in [
            MEDIA_TYPE_JSON,
            MEDIA_TYPE_TEXT,
        ]:
            raise ValueError(
                f"media_type must be either '{MEDIA_TYPE_JSON}' or '{MEDIA_TYPE_TEXT}'"
            )
        return self


class StreamingInterruptRequest(BaseModel):
    """Model representing a request to interrupt an active streaming query.

    Attributes:
        request_id: Unique ID of the active streaming request to interrupt.
    """

    request_id: str = Field(
        description="The active streaming request ID to interrupt",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )

    model_config = {
        "extra": "forbid",
        "json_schema_extra": {
            "examples": [
                {"request_id": "123e4567-e89b-12d3-a456-426614174000"},
            ]
        },
    }

    @field_validator("request_id")
    @classmethod
    def check_request_id(cls, value: str) -> str:
        """Validate that request identifier matches expected SUID format.

        Args:
            value: Request identifier submitted by the caller.

        Returns:
            The validated request identifier.

        Raises:
            ValueError: If the request identifier is not a valid SUID.
        """
        if not suid.check_suid(value):
            raise ValueError(f"Improper request ID {value}")
        return value

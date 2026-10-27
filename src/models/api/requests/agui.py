"""Request models for the AG-UI endpoint."""

from typing import Literal, Optional, Self

from ag_ui.core import RunAgentInput
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from models.common.query import SolrVectorSearchRequest


class AGUIForwardedProps(BaseModel):
    """Lightspeed-specific parameters passed via AG-UI forwardedProps."""

    provider: Optional[str] = Field(
        None,
        description="The optional provider",
        examples=["openai", "anthropic"],
    )

    model: Optional[str] = Field(
        None,
        description="The optional model",
        examples=["gpt-4o-mini"],
    )

    mode: Literal["client", "server"] = Field(
        default="client",
        description="Whether the client or the server should persist the conversation history",
    )

    system_prompt: Optional[str] = Field(
        None,
        description="The optional system prompt.",
        examples=["You are OpenShift assistant.", "You are Ansible assistant."],
    )

    # Not sure about this one
    no_tools: Optional[bool] = Field(
        False,
        description="Whether to bypass all tools and MCP servers",
        examples=[True, False],
    )

    # Might not need this
    vector_store_ids: Optional[list[str]] = Field(
        None,
        description="Optional list of specific vector store IDs to query for RAG. "
        "If not provided, all available vector stores will be queried.",
        examples=["ocp_docs", "knowledge_base", "vector_db_1"],
    )

    shield_ids: Optional[list[str]] = Field(
        None,
        description="Optional list of configured shield names to apply. "
        "If None, all configured shields are used.",
        examples=["topic-guard", "pii-redaction"],
    )

    # Might not need this
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

    model_config = ConfigDict(
        extra="allow",
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        # Even thought snake-case field names also work, but it's better we aligh with the
        # the camel-case naming style of AG-UI
        json_schema_extra={
            "examples": [
                {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "mode": "client",
                    "systemPrompt": "You are a helpful assistant",
                    "noTools": False,
                    "vectorStoreIds": ["ocp_docs", "knowledge_base"],
                    "shieldIds": ["topic-guard", "pii-redaction"],
                }
            ]
        },
    )

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


class AGUIRunAgentInput(RunAgentInput):
    """RunAgentInput with typed forwardedProps for Lightspeed."""

    forwarded_props: AGUIForwardedProps = Field(default=AGUIForwardedProps())

    model_config = ConfigDict(
        extra="allow",
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        # Even thought snake-case field names also work, but it's better we aligh with the
        # the camel-case naming style of AG-UI
        json_schema_extra={
            "examples": [
                {
                    "threadId": "123e4567-e89b-12d3-a456-426614174000",
                    "runId": "run-1",
                    "messages": [
                        {
                            "id": "msg-1",
                            "role": "user",
                            "content": "Write a deployment yaml for the mongodb image",
                        }
                    ],
                    "tools": [],
                    "context": [],
                    "forwardedProps": AGUIForwardedProps.model_json_schema()[
                        "examples"
                    ][0],
                }
            ]
        },
    )

"""Request parameter model for Llama Stack responses API calls."""

from collections.abc import Mapping
from typing import Any, Final, Optional

from llama_stack_api.openai_responses import (
    OpenAIResponseInputTool as InputTool,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolChoice as ToolChoice,
)
from llama_stack_api.openai_responses import (
    OpenAIResponsePrompt as Prompt,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseReasoning as Reasoning,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseText as Text,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseToolMCP as OutputToolMCP,
)
from pydantic import BaseModel, Field

from models.utils import add_mcp_authorizations
from utils.tool_formatter import translate_vector_store_ids_to_user_facing
from utils.types import IncludeParameter, ResponseInput

# Attribute names that are echoed back in the response.
_ECHOED_FIELDS: Final[set[str]] = set(
    {
        "instructions",
        "max_tool_calls",
        "max_output_tokens",
        "metadata",
        "model",
        "parallel_tool_calls",
        "previous_response_id",
        "prompt",
        "reasoning",
        "safety_identifier",
        "temperature",
        "top_p",
        "truncation",
        "text",
        "tool_choice",
        "store",
    }
)


class ResponsesApiParams(BaseModel):
    """Parameters for a Llama Stack Responses API request.

    All fields accepted by the Llama Stack client responses.create() body are
    included so that dumped model can be passed directly to response create.
    """

    input: ResponseInput = Field(description="The input text or structured input items")
    model: str = Field(description='The full model ID in format "provider/model"')
    conversation: str = Field(description="The conversation ID in llama-stack format")
    include: Optional[list[IncludeParameter]] = Field(
        default=None,
        description="Output item types to include in the response",
    )
    instructions: Optional[str] = Field(
        default=None, description="The resolved system prompt"
    )
    max_infer_iters: Optional[int] = Field(
        default=None,
        description="Maximum number of inference iterations",
    )
    max_output_tokens: Optional[int] = Field(
        default=None,
        description="Maximum number of tokens allowed in the response",
    )
    max_tool_calls: Optional[int] = Field(
        default=None,
        description="Maximum tool calls allowed in a single response",
    )
    metadata: Optional[dict[str, str]] = Field(
        default=None,
        description="Custom metadata for tracking or logging",
    )
    parallel_tool_calls: Optional[bool] = Field(
        default=None,
        description="Whether the model can make multiple tool calls in parallel",
    )
    previous_response_id: Optional[str] = Field(
        default=None,
        description="Identifier of the previous response in a multi-turn conversation",
    )
    prompt: Optional[Prompt] = Field(
        default=None,
        description="Prompt template with variables for dynamic substitution",
    )
    reasoning: Optional[Reasoning] = Field(
        default=None,
        description="Reasoning configuration for the response",
    )
    safety_identifier: Optional[str] = Field(
        default=None,
        description="Stable identifier for safety monitoring and abuse detection",
    )
    store: bool = Field(description="Whether to store the response")
    stream: bool = Field(description="Whether to stream the response")
    temperature: Optional[float] = Field(
        default=None,
        description="Sampling temperature (e.g. 0.0-2.0)",
    )
    text: Optional[Text] = Field(
        default=None,
        description="Text response configuration (format constraints)",
    )
    tool_choice: Optional[ToolChoice] = Field(
        default=None,
        description="Tool selection strategy",
    )
    tools: Optional[list[InputTool]] = Field(
        default=None,
        description="Prepared tool groups for Responses API (same type as ResponsesRequest.tools)",
    )
    extra_headers: Optional[dict[str, str]] = Field(
        default=None,
        description="Extra HTTP headers to send with the request (e.g. x-llamastack-provider-data)",
    )

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Serialize to a request body dict.

        Omits conversation when previous_response_id is set; restores MCP
        authorization on dumped tool rows.

        Returns:
            Serializable dict for the Responses API request body.
        """
        result = super().model_dump(*args, **kwargs)
        if self.previous_response_id:
            result.pop("conversation", None)
        if self.tools is not None and result.get("tools") is not None:
            result["tools"] = add_mcp_authorizations(result["tools"], self.tools)
        return result

    def echoed_params(self, rag_id_mapping: Mapping[str, str]) -> dict[str, Any]:
        """Build kwargs echoed into synthetic OpenAI-style responses (e.g. moderation blocks).

        Parameters:
            rag_id_mapping: Llama Stack vector_db_id to user-facing RAG id (from app config).
        Returns:
            dict[str, Any]: Field names and values to merge into the response object.
        """
        data = self.model_dump(include=_ECHOED_FIELDS)
        if self.tools is not None:
            tool_dicts: list[dict[str, Any]] = []
            for t in self.tools:
                if t.type == "mcp":
                    validated = OutputToolMCP.model_validate(t.model_dump())
                    tool_dicts.append(validated.model_dump())
                else:
                    tool_dicts.append(t.model_dump())

            data["tools"] = translate_vector_store_ids_to_user_facing(
                tool_dicts, rag_id_mapping
            )

        return data

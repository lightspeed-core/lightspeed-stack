"""Type aliases for OpenAI-compatible Responses API input shapes."""

from typing import Annotated, Literal, Optional

from llama_stack_api.openai_responses import (
    OpenAIResponseInputFunctionToolCallOutput as FunctionToolCallOutput,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolFileSearch as InputToolFileSearch,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolFunction as InputToolFunction,
)
from llama_stack_api.openai_responses import OpenAIResponseInputToolMCP
from llama_stack_api.openai_responses import (
    OpenAIResponseInputToolWebSearch as InputToolWebSearch,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseMCPApprovalRequest as McpApprovalRequest,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseMCPApprovalResponse as McpApprovalResponse,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseMessage as ResponseMessage,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutputMessageFileSearchToolCall as FileSearchToolCall,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutputMessageFunctionToolCall as FunctionToolCall,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutputMessageMCPCall as McpCall,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutputMessageMCPListTools as McpListTools,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutputMessageReasoningItem as ReasoningItem,
)
from llama_stack_api.openai_responses import (
    OpenAIResponseOutputMessageWebSearchToolCall as WebSearchToolCall,
)
from pydantic import Field


class InputToolMCP(OpenAIResponseInputToolMCP):
    """MCP input tool with authorization included when serializing request bodies."""

    authorization: Optional[str] = None


InputTool = Annotated[
    InputToolWebSearch | InputToolFileSearch | InputToolFunction | InputToolMCP,
    Field(discriminator="type"),
]

type IncludeParameter = Literal[
    "web_search_call.action.sources",
    "code_interpreter_call.outputs",
    "computer_call_output.output.image_url",
    "file_search_call.results",
    "message.input_image.image_url",
    "message.output_text.logprobs",
]

type ResponseItem = (
    ResponseMessage
    | WebSearchToolCall
    | FileSearchToolCall
    | FunctionToolCallOutput
    | McpCall
    | McpListTools
    | McpApprovalRequest
    | FunctionToolCall
    | McpApprovalResponse
    | ReasoningItem
)

type ResponseInput = str | list[ResponseItem]

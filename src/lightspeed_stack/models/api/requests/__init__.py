"""Concrete REST API request models grouped by domain."""

from lightspeed_stack.models.api.requests.catalog import ModelFilter
from lightspeed_stack.models.api.requests.conversations import ConversationUpdateRequest
from lightspeed_stack.models.api.requests.feedback import FeedbackRequest, FeedbackStatusUpdateRequest
from lightspeed_stack.models.api.requests.mcp_servers import MCPServerRegistrationRequest
from lightspeed_stack.models.api.requests.prompts import PromptCreateRequest, PromptUpdateRequest
from lightspeed_stack.models.api.requests.query import QueryRequest, StreamingInterruptRequest
from lightspeed_stack.models.api.requests.responses_openai import ResponsesRequest
from lightspeed_stack.models.api.requests.rlsapi import (
    RlsapiV1Attachment,
    RlsapiV1CLA,
    RlsapiV1Context,
    RlsapiV1InferRequest,
    RlsapiV1SystemInfo,
    RlsapiV1Terminal,
)
from lightspeed_stack.models.api.requests.vector_stores import (
    VectorStoreCreateRequest,
    VectorStoreFileCreateRequest,
    VectorStoreUpdateRequest,
)

__all__ = [
    "ConversationUpdateRequest",
    "FeedbackRequest",
    "FeedbackStatusUpdateRequest",
    "MCPServerRegistrationRequest",
    "ModelFilter",
    "PromptCreateRequest",
    "PromptUpdateRequest",
    "QueryRequest",
    "ResponsesRequest",
    "RlsapiV1Attachment",
    "RlsapiV1CLA",
    "RlsapiV1Context",
    "RlsapiV1InferRequest",
    "RlsapiV1SystemInfo",
    "RlsapiV1Terminal",
    "StreamingInterruptRequest",
    "VectorStoreCreateRequest",
    "VectorStoreFileCreateRequest",
    "VectorStoreUpdateRequest",
]

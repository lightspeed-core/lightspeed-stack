"""OpenAI API mapping utilities for the Responses API.

This module provides functions to convert between OpenAI-compatible request/response
formats and Lightspeed's internal QueryRequest/QueryResponse formats, enabling
OpenAI API compatibility while maintaining existing RAG and LLM integration.
"""

import time
from uuid import uuid4
from typing import Any

from models.requests import CreateResponseRequest, QueryRequest
from models.responses import (
    QueryResponse,
    OpenAIResponse,
    ResponseContent,
    ResponseMessage,
    ResponseOutput,
    ResponseUsage,
)


def map_openai_to_query_request(openai_request: CreateResponseRequest) -> QueryRequest:
    """Convert OpenAI CreateResponseRequest to internal QueryRequest format.

    Maps OpenAI request fields to Lightspeed's internal request structure,
    handling the conversion between OpenAI 'input' field and Lightspeed 'query' field.

    Args:
        openai_request: The OpenAI-compatible request to convert.

    Returns:
        QueryRequest: Internal Lightspeed request format.

    Raises:
        ValueError: If input format is not supported (MVP only supports string input).

    Example:
        ```python
        openai_req = CreateResponseRequest(
            model="gpt-4",
            input="What is Kubernetes?"
        )
        query_req = map_openai_to_query_request(openai_req)
        ```
    """
    # For MVP, only handle string input (arrays deferred to Phase 2)
    if isinstance(openai_request.input, list):
        raise ValueError("Array input not supported in MVP (Phase 1)")

    # Convert OpenAI input to Lightspeed query
    query = openai_request.input

    # Map OpenAI instructions to Lightspeed system_prompt
    system_prompt = openai_request.instructions

    # For MVP, use default model/provider (explicit model mapping in Phase 2)
    # This avoids the validation error where model requires provider
    model = None
    provider = None

    return QueryRequest(
        query=query,
        system_prompt=system_prompt,
        model=model,
        provider=provider,
        # MVP: Create new conversation each time (simplify conversation management)
        conversation_id=None,
        # MVP: Use defaults for optional fields
        attachments=None,
        no_tools=False,
        media_type=None,
    )


def map_query_to_openai_response(
    query_response: QueryResponse, openai_request: CreateResponseRequest
) -> OpenAIResponse:
    """Convert internal QueryResponse to OpenAI-compatible response format.

    Maps Lightspeed's internal response structure to OpenAI API format,
    preserving RAG document references in the metadata field.

    Args:
        query_response: The internal Lightspeed response to convert.
        openai_request: The original OpenAI request for context.

    Returns:
        OpenAIResponse: OpenAI-compatible response format.

    Example:
        ```python
        openai_response = map_query_to_openai_response(query_response, openai_request)
        ```
    """
    # Generate unique OpenAI response ID using uuid4
    response_id = f"resp_{uuid4().hex}"

    # Set appropriate created_at timestamp
    created_at = int(time.time())

    # Create response content structure
    content = [
        ResponseContent(
            type="text",
            text=query_response.response,
        )
    ]

    # Create response message
    message = ResponseMessage(
        role="assistant",
        content=content,
    )

    # Create response output
    output = [
        ResponseOutput(
            message=message,
            finish_reason="stop",  # MVP: default to "stop"
        )
    ]

    # Map token usage
    usage = ResponseUsage(
        prompt_tokens=query_response.input_tokens,
        completion_tokens=query_response.output_tokens,
        total_tokens=query_response.input_tokens + query_response.output_tokens,
    )

    # Map referenced documents to metadata
    metadata: dict[str, Any] | None = None
    if query_response.referenced_documents:
        # Convert ReferencedDocument objects to dict format
        referenced_docs = []
        for doc in query_response.referenced_documents:
            doc_dict = {
                "doc_url": str(doc.doc_url) if doc.doc_url else None,
                "doc_title": doc.doc_title,
            }
            referenced_docs.append(doc_dict)

        metadata = {"referenced_documents": referenced_docs}

    return OpenAIResponse(
        id=response_id,
        object="response",
        created_at=created_at,
        status="completed",  # MVP: default to "completed" for successful responses
        model=openai_request.model,
        output=output,
        usage=usage,
        metadata=metadata,
    )

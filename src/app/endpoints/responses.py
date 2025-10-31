"""Handler for REST API call to provide OpenAI-compatible responses endpoint."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from llama_stack_client import APIConnectionError

import constants
import metrics
from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from models.config import Action
from models.requests import CreateResponseRequest
from models.responses import (
    OpenAIResponse,
    ForbiddenResponse,
    UnauthorizedResponse,
    QueryResponse,
)
from utils.endpoints import check_configuration_loaded
from utils.openai_mapping import (
    map_openai_to_query_request,
    map_query_to_openai_response,
)
from app.endpoints.query import retrieve_response

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["responses"])

# Response definitions for OpenAPI documentation
responses_response_definitions: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "OpenAI-compatible response generated successfully",
        "model": OpenAIResponse,
    },
    400: {
        "description": "Missing or invalid credentials provided by client",
        "model": UnauthorizedResponse,
    },
    403: {
        "description": "User is not authorized",
        "model": ForbiddenResponse,
    },
    422: {
        "description": "Request validation failed",
        "content": {
            "application/json": {
                "example": {
                    "response": constants.UNABLE_TO_PROCESS_RESPONSE,
                    "cause": "Invalid input parameters or request format",
                }
            }
        },
    },
    500: {
        "description": "Internal server error",
        "content": {
            "application/json": {
                "example": {
                    "response": "Unable to connect to Llama Stack",
                    "cause": "Connection error.",
                }
            }
        },
    },
}


@router.post("/responses", responses=responses_response_definitions)
@authorize(Action.RESPONSES)
async def responses_endpoint_handler(
    request: Request,  # pylint: disable=unused-argument
    responses_request: CreateResponseRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> OpenAIResponse:
    """
    Handle request to the /responses endpoint.

    Processes a POST request to the /responses endpoint, providing OpenAI-compatible
    API responses while using Lightspeed's internal RAG and LLM integration.
    Converts OpenAI request format to internal QueryRequest, processes it through
    existing Lightspeed logic, and converts the response back to OpenAI format.

    This endpoint maintains full compatibility with the OpenAI Responses API
    specification while leveraging all existing Lightspeed functionality including
    authentication, authorization, RAG database queries, and LLM integration.

    Args:
        request: FastAPI Request object containing HTTP request details.
        responses_request: OpenAI-compatible request containing model, input, and options.
        auth: Authentication tuple containing user information and token.

    Returns:
        OpenAIResponse: OpenAI-compatible response with generated content and metadata.

    Raises:
        HTTPException: For connection errors (500) or other processing failures.

    Example:
        ```python
        # Request
        {
            "model": "gpt-4",
            "input": "What is Kubernetes?",
            "instructions": "You are a helpful DevOps assistant"
        }

        # Response
        {
            "id": "resp_67ccd2bed1ec8190b14f964abc0542670bb6a6b452d3795b",
            "object": "response",
            "created_at": 1640995200,
            "status": "completed",
            "model": "gpt-4",
            "output": [...],
            "usage": {...},
            "metadata": {"referenced_documents": [...]}
        }
        ```
    """
    check_configuration_loaded(configuration)

    # Extract authentication details
    user_id, _, _skip_userid_check, token = auth  # pylint: disable=unused-variable

    try:
        # Convert OpenAI request to internal QueryRequest format
        query_request = map_openai_to_query_request(responses_request)

        # Get Llama Stack client and retrieve response using existing logic
        client = AsyncLlamaStackClientHolder().get_client()

        # For MVP simplicity, use default model/provider selection logic from query.py
        # This will be enhanced in Phase 2 to support explicit model mapping
        summary, conversation_id, referenced_documents, token_usage = (
            await retrieve_response(
                client,
                responses_request.model,  # Pass model directly for now
                query_request,
                token,
                mcp_headers={},  # Empty for MVP
                provider_id="",  # Will be determined by existing logic
            )
        )

        # Create QueryResponse structure from TurnSummary for mapping

        internal_query_response = QueryResponse(
            conversation_id=conversation_id,
            response=summary.llm_response,
            rag_chunks=[],  # MVP: use empty list (summary.rag_chunks if available)
            tool_calls=None,  # MVP: simplified (summary.tool_calls if available)
            referenced_documents=referenced_documents,
            truncated=False,  # MVP: default to False
            input_tokens=token_usage.input_tokens,
            output_tokens=token_usage.output_tokens,
            available_quotas={},  # MVP: empty quotas
        )

        # Convert internal response to OpenAI format
        openai_response = map_query_to_openai_response(
            query_response=internal_query_response,
            openai_request=responses_request,
        )

        return openai_response

    except APIConnectionError as e:
        # Update metrics for the LLM call failure
        metrics.llm_calls_failures_total.inc()
        logger.error("Unable to connect to Llama Stack: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "response": "Unable to connect to Llama Stack",
                "cause": str(e),
            },
        ) from e
    except (ValueError, AttributeError, TypeError) as e:
        # Handle validation and mapping errors
        logger.error("Request validation or processing error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "response": constants.UNABLE_TO_PROCESS_RESPONSE,
                "cause": f"Invalid input parameters or request format: {str(e)}",
            },
        ) from e

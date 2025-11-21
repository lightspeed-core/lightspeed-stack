"""RHEL Lightspeed rlsapi v1 /infer - stateless inference (no history/caching/RAG)."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.params import Depends
from llama_stack_client import APIConnectionError

import constants
from app.endpoints.query import select_model_and_provider_id
from app.endpoints.query_v2 import extract_token_usage_from_responses_api
from authentication import get_auth_dependency
from authentication.interface import AuthTuple
from authorization.middleware import authorize
from client import AsyncLlamaStackClientHolder
from configuration import configuration
from models.config import Action
from models.requests import RlsapiV1InferRequest
from models.responses import RlsapiV1InferResponse
from utils.endpoints import check_configuration_loaded
from utils.responses import extract_text_from_response_output_item
from utils.quota import check_tokens_available, consume_tokens
from utils.suid import get_suid

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rlsapi_v1_infer"])

rlsapi_v1_infer_responses: dict[int | str, dict[str, Any]] = {
    200: {"description": "Successful inference"},
    401: {"description": "Authentication required"},
    403: {"description": "Not authorized"},
    422: {"description": "Invalid request"},
    429: {"description": "Quota exceeded"},
    500: {"description": "Llama Stack error"},
}


def format_v1_prompt(request: RlsapiV1InferRequest) -> str:
    """Format v1 request into prompt. Flexible dict-based context extraction.

    Args:
        request: The RHEL Lightspeed rlsapi v1 infer request

    Returns:
        Formatted prompt string with context and question
    """
    parts = []
    if request.context:
        # Extract common context fields (flexible - accept any keys!)
        if request.context.get("system_info"):
            parts.append(f"System: {request.context['system_info']}")
        if request.context.get("terminal_output"):
            parts.append(f"Terminal:\n{request.context['terminal_output']}")
        if request.context.get("stdin"):
            parts.append(f"Input:\n{request.context['stdin']}")
        if request.context.get("attachments"):
            att = request.context["attachments"]
            if isinstance(att, dict):
                mime = att.get("mimetype", "text/plain")
                content = att.get("contents", "")
            else:
                mime, content = "text/plain", str(att)
            parts.append(f"File ({mime}):\n{content}")
    parts.append(f"Question: {request.question}")
    return "\n\n".join(parts)


@router.post("/infer", responses=rlsapi_v1_infer_responses)
@authorize(Action.RLSAPI_V1_INFER)
async def rlsapi_v1_infer_endpoint_handler(  # pylint: disable=too-many-locals
    request: Request,
    infer_request: RlsapiV1InferRequest,
    auth: Annotated[AuthTuple, Depends(get_auth_dependency())],
) -> RlsapiV1InferResponse:
    """Handle v1 /infer - stateless LLM inference for RHEL Lightspeed rlsapi compatibility.

    Args:
        request: FastAPI request object (used by middleware)
        infer_request: The RHEL Lightspeed rlsapi v1 infer request
        auth: Authentication tuple (user_id, username, skip_userid_check, token)

    Returns:
        RHEL Lightspeed rlsapi v1 infer response with text and request_id

    Raises:
        HTTPException: For various error conditions (quota, no models, connection errors)
    """
    _ = request  # Used by middleware
    check_configuration_loaded(configuration)
    user_id, username, skip_userid_check, _ = auth
    logger.info("v1/infer request from user %s", username)

    try:
        # Respect skip_userid_check flag (e.g., noop auth skips quota)
        if not skip_userid_check:
            check_tokens_available(configuration.quota_limiters, user_id)

        try:
            client = AsyncLlamaStackClientHolder().get_client()
        except RuntimeError as e:
            logger.error("Llama Stack client not initialized: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "response": "Unable to initialize Llama Stack client",
                    "cause": str(e),
                },
            ) from e

        # Select model using existing utility (respects config defaults, handles errors)
        models = await client.models.list()
        model_id, model_label, provider_id = select_model_and_provider_id(
            models, None, None  # Use defaults from config
        )

        prompt = format_v1_prompt(infer_request)
        # Note: RlsapiV1InferRequest doesn't support per-request system prompts,
        # so we use config.customization.system_prompt with fallback to default
        # pylint: disable=no-member
        system_prompt = (
            configuration.customization.system_prompt
            if configuration.customization and configuration.customization.system_prompt
            else constants.DEFAULT_SYSTEM_PROMPT
        )
        # pylint: enable=no-member

        # Call Llama Stack Responses API (stateless, no storage)
        response = await client.responses.create(
            input=prompt,
            model=model_id,
            instructions=system_prompt,
            stream=False,
            store=False,
        )

        # Extract response text from ALL output items
        response_texts = [
            extract_text_from_response_output_item(output_item)
            for output_item in response.output
        ]
        response_text = "".join(text for text in response_texts if text)

        if not response_text:
            logger.warning("Empty response from Llama Stack")
            response_text = "I apologize, but I was unable to generate a response."

        # Extract token usage and update Prometheus metrics
        # Note: ResponseObject and OpenAIResponseObject are functionally equivalent
        token_counter = extract_token_usage_from_responses_api(
            response, model_label, provider_id, system_prompt  # type: ignore[arg-type]
        )
        logger.info(
            "v1/infer: %d in / %d out tokens",
            token_counter.input_tokens,
            token_counter.output_tokens,
        )
        # Consume tokens only when quota enforcement is active
        if not skip_userid_check:
            consume_tokens(
                configuration.quota_limiters,
                user_id,
                input_tokens=token_counter.input_tokens,
                output_tokens=token_counter.output_tokens,
            )

        return RlsapiV1InferResponse(
            data={
                "text": response_text,
                "request_id": get_suid(),
            }
        )

    except APIConnectionError as e:
        logger.error("Llama Stack connection error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"response": "Unable to connect to Llama Stack", "cause": str(e)},
        ) from e

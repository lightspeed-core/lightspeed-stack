"""Handler for REST API call to provide answer to query."""

from datetime import datetime, UTC
import json
import logging
import os
from pathlib import Path
from typing import Any

from llama_stack_client.lib.agents.agent import Agent  # type: ignore
from llama_stack_client import LlamaStackClient  # type: ignore
from llama_stack_client.types import UserMessage  # type: ignore
from llama_stack_client.types.model_list_response import ModelListResponse

from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import StreamingResponse

from client import get_llama_stack_client
from configuration import configuration
from models.responses import QueryResponse
from models.requests import QueryRequest, Attachment
import constants
from utils.auth import auth_dependency
from utils.common import retrieve_user_id
from utils.suid import get_suid

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["query"])


query_response: dict[int | str, dict[str, Any]] = {
    200: {
        "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
        "response": "LLM ansert",
    },
}


def is_transcripts_enabled() -> bool:
    """Check if transcripts is enabled.

    Returns:
        bool: True if transcripts is enabled, False otherwise.
    """
    return not configuration.user_data_collection_configuration.transcripts_disabled


def retrieve_conversation_id(query_request: QueryRequest) -> str:
    """Retrieve conversation ID based on existing ID or on newly generated one."""
    conversation_id = query_request.conversation_id

    # Generate a new conversation ID if not provided
    if not conversation_id:
        conversation_id = get_suid()
        logger.info("Generated new conversation ID: %s", conversation_id)

    return conversation_id


def format_stream_data(d: dict) -> str:
    """Format outbound data in the Event Stream Format."""
    data = json.dumps(d)
    return f"data: {data}\n\n"

def stream_start_event(conversation_id: str) -> str:
    """Yield the start of the data stream.

    Args:
        conversation_id: The conversation ID (UUID).
    """
    return format_stream_data(
        {
            "event": "start",
            "data": {
                "conversation_id": conversation_id,
            },
        }
    )

def stream_end_event() -> str:
    """Yield the end of the data stream."""
    return format_stream_data(
        {
            "event": "end",
            "data": {
                "referenced_documents": None,
                "truncated": None,
                "input_tokens": 0,
                "output_tokens": 0,
            },
            "available_quotas": {},
        }
    )

@router.post("/streaming_query", responses=query_response)
async def streaming_query_endpoint_handler(
    _request: Request,
    query_request: QueryRequest,
    auth: Any = Depends(auth_dependency),
) -> StreamingResponse:
    """Handle request to the /query endpoint."""
    llama_stack_config = configuration.llama_stack_configuration
    logger.info("LLama stack config: %s", llama_stack_config)
    client = get_llama_stack_client(llama_stack_config)
    model_id = select_model_id(client, query_request)
    conversation_id = retrieve_conversation_id(query_request)
    response = retrieve_response(client, model_id, query_request)

    def response_generator(turn_response):
        """Generate SSE formatted streaming response."""
        token_id = 0
        complete_response = ""
        
        # Send start event
        yield stream_start_event(conversation_id)
        
        for res in turn_response:
            if hasattr(res.event, "payload"):
                if res.event.payload.event_type == "step_progress":
                    if hasattr(res.event.payload.delta, "text"):
                        text = res.event.payload.delta.text
                        yield format_stream_data(
                            {
                                "event": "token",
                                "data": {"id": token_id, "token": text}
                            }
                        )
                        token_id += 1
                        complete_response += text
            else:
                # Handle errors in the same SSE format
                yield format_stream_data(
                    {
                        "event": "error",
                        "data": {
                            "status_code": 500,
                            "response": "Error occurred in the Llama Stack",
                            "cause": res,
                        }
                    }
                )
                return
        yield stream_end_event()
        
        if not is_transcripts_enabled():
            logger.debug("Transcript collection is disabled in the configuration")
        else:
            store_transcript(
                user_id=retrieve_user_id(auth),
                conversation_id=conversation_id,
                query_is_valid=True,  # TODO(lucasagomes): implement as part of query validation
                query=query_request.query,
                query_request=query_request,
                response=complete_response,
                rag_chunks=[],  # TODO(lucasagomes): implement rag_chunks
                truncated=False,  # TODO(lucasagomes): implement truncation as part of quota work
                attachments=query_request.attachments or [],
            )

    return StreamingResponse(
        response_generator(response)
    )

def select_model_id(client: LlamaStackClient, query_request: QueryRequest) -> str:
    """Select the model ID based on the request or available models."""
    models: ModelListResponse = client.models.list()
    model_id = query_request.model
    provider_id = query_request.provider

    # TODO(lucasagomes): support default model selection via configuration
    if not model_id:
        logger.info("No model specified in request, using the first available LLM")
        try:
            model = next(
                m
                for m in models
                if m.model_type == "llm"  # pyright: ignore[reportAttributeAccessIssue]
            ).identifier
            logger.info("Selected model: %s", model)
            return model
        except (StopIteration, AttributeError) as e:
            message = "No LLM model found in available models"
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "response": constants.UNABLE_TO_PROCESS_RESPONSE,
                    "cause": message,
                },
            ) from e

    logger.info("Searching for model: %s, provider: %s", model_id, provider_id)
    if not any(
        m.identifier == model_id and m.provider_id == provider_id for m in models
    ):
        message = f"Model {model_id} from provider {provider_id} not found in available models"
        logger.error(message)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "response": constants.UNABLE_TO_PROCESS_RESPONSE,
                "cause": message,
            },
        )

    return model_id


def retrieve_response(
    client: LlamaStackClient, model_id: str, query_request: QueryRequest
):
    """Retrieve response from LLMs and agents."""
    available_shields = [shield.identifier for shield in client.shields.list()]
    if not available_shields:
        logger.info("No available shields. Disabling safety")
    else:
        logger.info("Available shields found: %s", available_shields)

    # use system prompt from request or default one
    system_prompt = (
        query_request.system_prompt
        if query_request.system_prompt
        else constants.DEFAULT_SYSTEM_PROMPT
    )
    logger.debug("Using system prompt: %s", system_prompt)

    # TODO(lucasagomes): redact attachments content before sending to LLM
    # if attachments are provided, validate them
    if query_request.attachments:
        validate_attachments_metadata(query_request.attachments)

    agent = Agent(
        client,
        model=model_id,
        instructions=system_prompt,
        input_shields=available_shields if available_shields else [],
        tools=[],
    )
    session_id = agent.create_session("chat_session")
    logger.debug("Session ID: %s", session_id)
    response = agent.create_turn(
        messages=[UserMessage(role="user", content=query_request.query)],
        session_id=session_id,
        documents=query_request.get_documents(),
        stream=True,
    )

    return response

def validate_attachments_metadata(attachments: list[Attachment]) -> None:
    """Validate the attachments metadata provided in the request.

    Raises HTTPException if any attachment has an improper type or content type.
    """
    for attachment in attachments:
        if attachment.attachment_type not in constants.ATTACHMENT_TYPES:
            message = (
                f"Attachment with improper type {attachment.attachment_type} detected"
            )
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "response": constants.UNABLE_TO_PROCESS_RESPONSE,
                    "cause": message,
                },
            )
        if attachment.content_type not in constants.ATTACHMENT_CONTENT_TYPES:
            message = f"Attachment with improper content type {attachment.content_type} detected"
            logger.error(message)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "response": constants.UNABLE_TO_PROCESS_RESPONSE,
                    "cause": message,
                },
            )


def construct_transcripts_path(user_id: str, conversation_id: str) -> Path:
    """Construct path to transcripts."""
    # these two normalizations are required by Snyk as it detects
    # this Path sanitization pattern
    uid = os.path.normpath("/" + user_id).lstrip("/")
    cid = os.path.normpath("/" + conversation_id).lstrip("/")
    file_path = (
        configuration.user_data_collection_configuration.transcripts_storage or ""
    )
    return Path(file_path, uid, cid)


def store_transcript(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    user_id: str,
    conversation_id: str,
    query_is_valid: bool,
    query: str,
    query_request: QueryRequest,
    response: str,
    rag_chunks: list[str],
    truncated: bool,
    attachments: list[Attachment],
) -> None:
    """Store transcript in the local filesystem.

    Args:
        user_id: The user ID (UUID).
        conversation_id: The conversation ID (UUID).
        query_is_valid: The result of the query validation.
        query: The query (without attachments).
        query_request: The request containing a query.
        response: The response to store.
        rag_chunks: The list of `RagChunk` objects.
        truncated: The flag indicating if the history was truncated.
        attachments: The list of `Attachment` objects.
    """
    transcripts_path = construct_transcripts_path(user_id, conversation_id)
    transcripts_path.mkdir(parents=True, exist_ok=True)

    data_to_store = {
        "metadata": {
            "provider": query_request.provider,
            "model": query_request.model,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        "redacted_query": query,
        "query_is_valid": query_is_valid,
        "llm_response": response,
        "rag_chunks": rag_chunks,
        "truncated": truncated,
        "attachments": [attachment.model_dump() for attachment in attachments],
    }

    # stores feedback in a file under unique uuid
    transcript_file_path = transcripts_path / f"{get_suid()}.json"
    with open(transcript_file_path, "w", encoding="utf-8") as transcript_file:
        json.dump(data_to_store, transcript_file)

    logger.info("Transcript successfully stored at: %s", transcript_file_path)

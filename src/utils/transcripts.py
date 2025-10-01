"""Transcript handling.

Transcripts are a log of individual query/response pairs that get
stored on disk for later analysis
"""

from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path

from configuration import configuration
from models.requests import Attachment, QueryRequest
from utils.suid import get_suid
from utils.types import TurnSummary

logger = logging.getLogger("utils.transcripts")


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


def store_transcript(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    user_id: str,
    conversation_id: str,
    model_id: str,
    provider_id: str | None,
    query_is_valid: bool,
    query: str,
    query_request: QueryRequest,
    summary: TurnSummary,
    rag_chunks: list[dict],
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
        summary: Summary of the query/response turn.
        rag_chunks: The list of serialized `RAGChunk` dictionaries.
        truncated: The flag indicating if the history was truncated.
        attachments: The list of `Attachment` objects.
    """
    transcripts_path = construct_transcripts_path(user_id, conversation_id)
    transcripts_path.mkdir(parents=True, exist_ok=True)

    data_to_store = {
        "metadata": {
            "provider": provider_id,
            "model": model_id,
            "query_provider": query_request.provider,
            "query_model": query_request.model,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        "redacted_query": query,
        "query_is_valid": query_is_valid,
        "llm_response": summary.llm_response,
        "rag_chunks": rag_chunks,
        "truncated": truncated,
        "attachments": [attachment.model_dump() for attachment in attachments],
        "tool_calls": [tc.model_dump() for tc in summary.tool_calls],
    }

    # stores feedback in a file under unique uuid
    transcript_file_path = transcripts_path / f"{get_suid()}.json"
    try:
        with open(transcript_file_path, "w", encoding="utf-8") as transcript_file:
            json.dump(data_to_store, transcript_file)
    except (IOError, OSError) as e:
        logger.error("Failed to store transcript into %s: %s", transcript_file_path, e)
        raise

    logger.info("Transcript successfully stored at: %s", transcript_file_path)

"""Transcript handling.

Transcripts are a log of individual query/response pairs that get
stored on disk for later analysis
"""

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import hashlib

from fastapi import HTTPException

from configuration import configuration

from models.requests import Attachment
from models.responses import InternalServerErrorResponse
from utils.suid import get_suid
from utils.types import (
    Transcript,
    TranscriptMetadata,
    TurnSummary,
)
from log import get_logger

logger = get_logger(__name__)


def _hash_user_id(user_id: str) -> str:
    """Hash the user ID using SHA-256.

    Return the SHA-256 hex digest of the given user_id.

    Parameters:
        user_id (str): The user identifier to hash.

    Returns:
        str: Hexadecimal SHA-256 digest of the UTF-8 encoded user_id.
    """
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()


def construct_transcripts_path(hashed_user_id: str, conversation_id: str) -> Path:
    """
    Construct the filesystem path where transcripts for a given user and conversation are stored.

    The returned path is built from the configured transcripts storage base
    directory, a filesystem-safe directory derived from a pre-hashed `user_id`,
    and a filesystem-safe form of `conversation_id`.

    Parameters:
        hashed_user_id (str): The hashed identifier for the user
        conversation_id (str): The conversation identifier; this value is
                               normalized for use as a path component.

    Returns:
        Path: A Path pointing to the directory where transcripts for the
        specified user and conversation should be stored.
    """
    # these two normalizations are required by Snyk as it detects
    # this Path sanitization pattern
    uid = os.path.normpath("/" + hashed_user_id).lstrip("/")
    cid = os.path.normpath("/" + conversation_id).lstrip("/")
    file_path = (
        configuration.user_data_collection_configuration.transcripts_storage or ""
    )
    return Path(file_path, uid, cid)


def store_transcript(
    transcript: Transcript,
) -> None:
    """Store transcript in the local filesystem.

    Parameters:
        transcript: BaseModel instance to be stored (e.g., Transcript).

    Raises:
        HTTPException: If writing the transcript file to disk fails.
    """
    transcripts_path = construct_transcripts_path(
        transcript.metadata.user_id, transcript.metadata.conversation_id
    )
    transcripts_path.mkdir(parents=True, exist_ok=True)

    # stores transcript in a file under unique uuid
    transcript_file_path = transcripts_path / f"{get_suid()}.json"
    try:
        with open(transcript_file_path, "w", encoding="utf-8") as transcript_file:
            json.dump(transcript.model_dump(), transcript_file)
        logger.info("Transcript successfully stored at: %s", transcript_file_path)
    except (IOError, OSError) as e:
        logger.error("Failed to store transcript into %s: %s", transcript_file_path, e)
        response = InternalServerErrorResponse.generic()
        raise HTTPException(**response.model_dump()) from e


def create_transcript_metadata(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    user_id: str,
    conversation_id: str,
    model_id: str,
    provider_id: str | None,
    query_provider: str | None,
    query_model: str | None,
) -> TranscriptMetadata:
    """Create a TranscriptMetadata BaseModel instance.

    Parameters:
        user_id: The user ID (UUID).
        conversation_id: The conversation ID (UUID).
        model_id: Identifier of the model used to generate the LLM response.
        provider_id: Optional provider identifier for the model.
        query_provider: Optional provider identifier from the query request.
        query_model: Optional model identifier from the query request.

    Returns:
        TranscriptMetadata: A TranscriptMetadata BaseModel instance.
    """
    hashed_user_id = _hash_user_id(user_id)

    return TranscriptMetadata(
        provider=provider_id,
        model=model_id,
        query_provider=query_provider,
        query_model=query_model,
        user_id=hashed_user_id,
        conversation_id=conversation_id,
        timestamp=datetime.now(UTC).isoformat(),
    )


def create_transcript(
    metadata: TranscriptMetadata,
    redacted_query: str,
    summary: TurnSummary,
    attachments: list[Attachment],
) -> Transcript:
    """Create a Transcript BaseModel instance from individual parameters.

    Parameters:
        metadata: The transcript metadata.
        redacted_query: The query text (redacted if necessary).
        summary: Summary of the query/response turn containing LLM response,
                RAG chunks, tool calls, and tool results.
        attachments: List of attachments from the query request.

    Returns:
        Transcript: A Transcript BaseModel instance ready to be stored.
    """
    return Transcript(
        metadata=metadata,
        redacted_query=redacted_query,
        query_is_valid=True,
        llm_response=summary.llm_response,
        rag_chunks=[chunk.model_dump() for chunk in summary.rag_chunks],
        truncated=False,
        attachments=[attachment.model_dump() for attachment in attachments],
        tool_calls=[tc.model_dump() for tc in summary.tool_calls],
        tool_results=[tr.model_dump() for tr in summary.tool_results],
    )

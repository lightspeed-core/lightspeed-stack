"""Transcript handling.

Transcripts are a log of individual query/response pairs that get
stored on disk for later analysis
"""

from datetime import UTC, datetime
import fcntl
import json
import logging
import os
from pathlib import Path

from configuration import configuration
from models.requests import Attachment, QueryRequest
from utils.types import TurnSummary

logger = logging.getLogger("utils.transcripts")


def construct_transcripts_path(user_id: str) -> Path:
    """Construct path to transcripts."""
    # these two normalizations are required by Snyk as it detects
    # this Path sanitization pattern
    uid = os.path.normpath("/" + user_id).lstrip("/")
    file_path = (
        configuration.user_data_collection_configuration.transcripts_storage or ""
    )
    return Path(file_path, uid)


def store_transcript(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    user_id: str,
    conversation_id: str,
    model_id: str,
    provider_id: str | None,
    query_is_valid: bool,
    query: str,
    query_request: QueryRequest,
    summary: TurnSummary,
    rag_chunks: list[str],
    truncated: bool,
    attachments: list[Attachment],
) -> None:
    """Store transcript in the local filesystem.

    All turns for a single conversation are stored in the same file,
    named after the conversation_id.

    Args:
        user_id: The user ID (UUID).
        conversation_id: The conversation ID (UUID).
        model_id: The model ID.
        provider_id: The provider ID.
        query_is_valid: The result of the query validation.
        query: The query (without attachments).
        query_request: The request containing a query.
        summary: Summary of the query/response turn.
        rag_chunks: The list of `RagChunk` objects.
        truncated: The flag indicating if the history was truncated.
        attachments: The list of `Attachment` objects.
    """
    transcripts_path = construct_transcripts_path(user_id)
    transcripts_path.mkdir(parents=True, exist_ok=True)

    # Use conversation_id as filename instead of random UUID
    transcript_file_path = transcripts_path / f"{conversation_id}.json"
    # Prepare turn data
    turn_data = {
        "metadata": {
            "provider": provider_id,
            "model": model_id,
            "query_provider": query_request.provider,
            "query_model": query_request.model,
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

    # Use file locking to handle concurrent writes safely
    with open(transcript_file_path, "a+", encoding="utf-8") as transcript_file:
        fcntl.flock(transcript_file.fileno(), fcntl.LOCK_EX)
        try:
            # Move to beginning to read existing content
            transcript_file.seek(0)
            file_content = transcript_file.read()
            if file_content.strip():
                # File has existing content, load it
                transcript_file.seek(0)
                conversation_data = json.load(transcript_file)
            else:
                # First turn for this conversation
                conversation_data = {
                    "conversation_metadata": {
                        "conversation_id": conversation_id,
                        "user_id": user_id,
                        "created_at": datetime.now(UTC).isoformat(),
                        "last_updated": datetime.now(UTC).isoformat(),
                    },
                    "turns": [],
                }
            # Add new turn
            conversation_data["turns"].append(turn_data)
            conversation_data["conversation_metadata"]["last_updated"] = datetime.now(
                UTC
            ).isoformat()

            # Write updated data back to file
            transcript_file.seek(0)
            transcript_file.truncate()
            json.dump(conversation_data, transcript_file, indent=2)
        finally:
            fcntl.flock(transcript_file.fileno(), fcntl.LOCK_UN)

    logger.info("Transcript turn successfully stored at: %s", transcript_file_path)

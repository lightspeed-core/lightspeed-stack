# Pydantic model utilization

class TranscriptMetadata(BaseModel):
    """Metadata for a transcript entry."""

    provider: Optional[str] = None
    model: str
    query_provider: Optional[str] = None
    query_model: Optional[str] = None
    user_id: str
    conversation_id: str
    timestamp: str


def create_transcript_metadata(
    user_id: str,
    conversation_id: str,
    model_id: str,
    provider_id: Optional[str],
    query_provider: Optional[str],
    query_model: Optional[str],
) -> TranscriptMetadata:
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


# Pydantic model utilization

class ShieldModerationBlocked(BaseModel):
    """Shield moderation blocked the content; refusal details are present."""

    decision: Literal["blocked"] = "blocked"
    message: str
    moderation_id: str
    refusal_response: ResponseMessage

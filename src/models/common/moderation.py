"""Shield moderation outcomes for the responses pipeline."""

from typing import Annotated, Literal

from ogx_api.openai_responses import (
    OpenAIResponseMessage as ResponseMessage,
)
from pydantic import BaseModel, Field


class ShieldModerationPassed(BaseModel):
    """Shield moderation passed; no refusal."""

    decision: Literal["passed"] = "passed"


class ShieldModerationBlocked(BaseModel):
    """Shield moderation blocked the content; refusal details are present."""

    decision: Literal["blocked"] = "blocked"
    message: str
    moderation_id: str
    refusal_response: ResponseMessage


ShieldModerationResult = Annotated[
    ShieldModerationPassed | ShieldModerationBlocked,
    Field(discriminator="decision"),
]


class ShieldModerationPassedV2(BaseModel):
    """Shield moderation passed; no refusal."""

    decision: Literal["passed"] = "passed"


class ShieldModerationBlockedV2(BaseModel):
    """Shield moderation blocked the content; refusal details are present."""

    decision: Literal["blocked"] = "blocked"
    message: str


ShieldModerationResultV2 = Annotated[
    ShieldModerationPassedV2 | ShieldModerationBlockedV2,
    Field(discriminator="decision"),
]

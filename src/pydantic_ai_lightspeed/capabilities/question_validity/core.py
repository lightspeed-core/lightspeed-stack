"""Core question-validity classification (no Pydantic AI capability wiring)."""

from __future__ import annotations

from string import Template

from ogx_client import AsyncOgxClient
from pydantic import BaseModel, ConfigDict
from pydantic_ai.direct import model_request
from pydantic_ai.messages import ModelRequest
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from models.config import QuestionValidityConfig
from pydantic_ai_lightspeed.llamastack import OgxResponsesModel

SUBJECT_REJECTED = "REJECTED"
SUBJECT_ALLOWED = "ALLOWED"


class QuestionValidityResult(BaseModel):
    """Outcome of a question-validity classification.

    Attributes:
        allowed: True when the classifier returned the allowed token.
        classifier_text: Raw classifier response text, if any.
    """

    model_config = ConfigDict(frozen=True)

    allowed: bool
    classifier_text: str | None = None


def build_question_validity_prompt(message: str, config: QuestionValidityConfig) -> str:
    """Build the classification prompt for the validity model.

    Args:
        message: User input text to classify.
        config: Question validity configuration with prompt template.

    Returns:
        Rendered prompt string.
    """
    return Template(config.model_prompt).substitute(
        message=message,
        allowed=SUBJECT_ALLOWED,
        rejected=SUBJECT_REJECTED,
    )


async def classify_question_validity(
    model: Model,
    prompt: str,
) -> QuestionValidityResult:
    """Classify a question using an already-constructed model.

    Args:
        model: Validity model instance.
        prompt: Fully rendered classification prompt.

    Returns:
        QuestionValidityResult indicating whether the question is allowed.
    """
    result = await model_request(
        model=model,
        messages=[ModelRequest.user_text_prompt(prompt)],
    )
    classifier_text = result.text
    allowed = classifier_text is not None and classifier_text.strip() == SUBJECT_ALLOWED
    return QuestionValidityResult(
        allowed=allowed,
        classifier_text=classifier_text,
    )


async def check_question_validity(
    text: str,
    config: QuestionValidityConfig,
    *,
    client: AsyncOgxClient,
) -> QuestionValidityResult:
    """Run question-validity classification for plain text input.

    Args:
        text: User input to classify.
        config: Question validity configuration.
        client: OGX client used to construct the validity model.

    Returns:
        QuestionValidityResult indicating whether the question is allowed.
    """
    model = OgxResponsesModel.from_ogx_client(
        config.model_id,
        client,
        model_settings=OpenAIResponsesModelSettings(openai_store=False),
    )
    prompt = build_question_validity_prompt(text, config)
    return await classify_question_validity(model, prompt)

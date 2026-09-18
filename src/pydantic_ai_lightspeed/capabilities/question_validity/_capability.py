"""Question validity capability for filtering off-topic user queries.

This module implements a guardrail that classifies user questions as
Kubernetes/OpenShift-related or not (It can be customized to any
topic as well), using an LLM-based check before the main agent
processes the request. Invalid questions are rejected with a
predefined response, bypassing the primary agent entirely.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from string import Template
from typing import Optional
from uuid import uuid4

from pydantic_ai import AgentRunResult, RunContext
from pydantic_ai._agent_graph import GraphAgentState
from pydantic_ai.capabilities import WrapRunHandler
from pydantic_ai.direct import model_request
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserContent,
)
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from client.ogx import AsyncOgxClientHolder
from log import get_logger
from models.common.moderation import (
    ShieldModerationBlocked,
    ShieldModerationPassed,
    ShieldModerationResult,
)
from models.config import (
    QuestionValidityConfig,
)
from pydantic_ai_lightspeed.capabilities.base import AbstractSafetyCapability
from pydantic_ai_lightspeed.capabilities.utils import (
    extract_conversation_id,
    message_to_str,
)
from pydantic_ai_lightspeed.ogx import OgxResponsesModel
from utils.conversations import append_turn_to_conversation

logger = get_logger(__name__)

SUBJECT_REJECTED = "REJECTED"
SUBJECT_ALLOWED = "ALLOWED"


@dataclass
class QuestionValidity(AbstractSafetyCapability):
    """Block or modify user input based on a guardrail check.

    The guard function receives the user prompt and returns True if safe.

    Example:
        ```python
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIResponsesModel

        model = OpenAIResponsesModel("gpt-4o-mini")
        agent = Agent("openai:gpt-4.1", capabilities=[QuestionValidity(model)])
        ```
    """

    config: QuestionValidityConfig
    _model: Model = field(init=False)

    def __post_init__(self) -> None:
        """Initialize the model instance from the configured model ID."""
        ogx_client = AsyncOgxClientHolder().get_client()

        self._model = OgxResponsesModel.from_ogx_client(
            self.config.model_id,
            ogx_client,
            model_settings=OpenAIResponsesModelSettings(openai_store=False),
        )

    def _build_prompt(self, message: Optional[str | Sequence[UserContent]]) -> str:
        """Build the classification prompt from the user message.

        Parameters:
            message: The user input as a string, sequence of user content, or None.

        Returns:
            The rendered prompt string ready to send to the validity model.
        """
        return Template(self.config.model_prompt).substitute(
            message=message_to_str(message),
            allowed=SUBJECT_ALLOWED,
            rejected=SUBJECT_REJECTED,
        )

    async def wrap_run(
        self, ctx: RunContext, *, handler: WrapRunHandler
    ) -> AgentRunResult:
        """Run the question validity check before delegating to the main agent.

        Sends the user prompt to the validity model for classification.
        If the question is allowed, the handler proceeds normally.
        Otherwise, a rejection response is returned and the main agent
        is bypassed.

        Parameters:
            ctx: The run context containing the user prompt and usage tracker.
            handler: The handler that invokes the main agent run.

        Returns:
            The agent run result, either from the main agent or a rejection.
        """
        prompt = self._build_prompt(ctx.prompt)

        result = await model_request(
            model=self._model,
            messages=[ModelRequest.user_text_prompt(prompt)],
        )

        # Include token usage from the question validity request
        ctx.usage.incr(result.usage)

        if result.text is not None and result.text.strip() == SUBJECT_ALLOWED:
            return await handler()  # proceed with the real run

        # short-circuit: return the rejection message with shield usage tracked
        user_message = message_to_str(ctx.prompt)
        state = GraphAgentState(
            usage=ctx.usage,
            message_history=[
                ModelRequest.user_text_prompt(user_message),
                ModelResponse(
                    [TextPart(self.config.invalid_question_response)],
                    finish_reason="stop",
                ),
            ],
        )

        conversation_id = extract_conversation_id(ctx.model)
        if conversation_id is not None:
            await append_turn_to_conversation(
                AsyncOgxClientHolder().get_client(),
                conversation_id,
                user_message,
                self.config.invalid_question_response,
            )
        else:
            logger.warning(
                "Unable to determine conversation ID from model settings; "
                "skipping v1/conversation persistence for rejected question."
            )

        return AgentRunResult(
            output=self.config.invalid_question_response, _state=state
        )

    async def run(self, input_text: str) -> ShieldModerationResult:
        """Run question-validity check and return a moderation result."""
        prompt = self._build_prompt(input_text)
        result = await model_request(
            model=self._model, messages=[ModelRequest.user_text_prompt(prompt)]
        )

        if result.text is not None and result.text.strip() == SUBJECT_ALLOWED:
            return ShieldModerationPassed()

        return ShieldModerationBlocked(
            message=self.config.invalid_question_response,
            moderation_id=f"modr-{uuid4()}",
        )

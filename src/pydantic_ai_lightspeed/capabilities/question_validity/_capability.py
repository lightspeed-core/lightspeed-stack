"""Question validity capability for filtering off-topic user queries.

This module implements a guardrail that classifies user questions as
Kubernetes/OpenShift-related or not (It can be customized to any
topic as well), using an LLM-based check before the main agent
processes the request. Invalid questions are rejected with a
predefined response, bypassing the primary agent entirely.
"""

from __future__ import annotations

from collections.abc import Sequence
from copy import copy
from dataclasses import dataclass
from string import Template

from pydantic_ai import AgentRunResult, RunContext
from pydantic_ai._agent_graph import GraphAgentState
from pydantic_ai.capabilities import AbstractCapability, WrapRunHandler
from pydantic_ai.direct import model_request
from pydantic_ai.messages import ModelRequest, TextContent, UserContent
from pydantic_ai.models import Model

from log import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL_PROMPT = """
Instructions:
- You are a question classifying tool
- You are an expert in kubernetes and openshift
- Your job is to determine where or a user's question is related to kubernetes and/or openshift technologies and to provide a one-word response.
- If a question appears to be related to kubernetes or openshift technologies, answer with the word ${allowed}, otherwise answer with the word ${rejected}.
- Do not explain your answer, just provide the one-word response. Do not give any other response.
- If the given question is an empty string, answer with the word ${rejected}


Example Question:
Why is the sky blue?
Example Response:
${rejected}

Example Question:
Why is the grass green?
Example Response:
${rejected}

Example Question:
Why is sand yellow?
Example Response:
${rejected}

Example Question:
Can you help configure my cluster to automatically scale?
Example Response:
${allowed}

Question:
${message}
Response:
"""

DEFAULT_INVALID_QUESTION_RESPONSE = """
Hi, I'm the OpenShift Lightspeed assistant, I can help you with questions about OpenShift, 
please ask me a question related to OpenShift.
"""

SUBJECT_REJECTED = "REJECTED"
SUBJECT_ALLOWED = "ALLOWED"


def _extract_message_str_from_user_content(user_content: Sequence[UserContent]) -> str:
    """Extract and combine all text content into a string from an UserContent sequence"""
    str_arr: list[str] = []
    for c in user_content:
        match c:
            case str() as s:
                str_arr.append(s)
            case TextContent(content=c):
                str_arr.append(c)

    return "\n".join(str_arr)


def _remove_conversation_from_settings(model: Model) -> Model:
    """Return a Model with 'conversation' removed from extra_body settings.

    Only creates a shallow copy if 'conversation' exists in extra_body; otherwise returns the original model unchanged.
    """
    if settings := model.settings:
        if extra_body := settings.get("extra_body"):
            if isinstance(extra_body, dict) and "conversation" in extra_body:
                _extra_body = {
                    k: v for k, v in extra_body.items() if k != "conversation"
                }
                _settings = copy(settings)
                _settings["extra_body"] = _extra_body
                _model = copy(model)
                _model._settings = _settings
                return _model
    return model


@dataclass
class QuestionValidity(AbstractCapability):
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

    model: Model
    """The model to use for the question validity check."""

    model_prompt: str = DEFAULT_MODEL_PROMPT
    """The prompt to use for the question validity check."""

    invalid_question_response: str = DEFAULT_INVALID_QUESTION_RESPONSE
    """The response to use when the question is determined to be invalid."""

    def __post_init__(self) -> None:
        self.model = _remove_conversation_from_settings(self.model)

    def _build_prompt(self, message: str | Sequence[UserContent] | None) -> str:
        match message:
            case str() as s:
                _message = s
            case Sequence() as seq:
                _message = _extract_message_str_from_user_content(seq)
            case None:
                _message = ""

        return Template(self.model_prompt).substitute(
            message=_message, allowed=SUBJECT_ALLOWED, rejected=SUBJECT_REJECTED
        )

    async def wrap_run(
        self, ctx: RunContext, *, handler: WrapRunHandler
    ) -> AgentRunResult:
        prompt = self._build_prompt(ctx.prompt)

        result = await model_request(
            model=self.model,
            messages=[ModelRequest.user_text_prompt(prompt)],
        )

        # Include token usage from the question validity request
        ctx.usage.incr(result.usage)

        if result.text == SUBJECT_ALLOWED:
            return await handler()  # proceed with the real run
        else:
            # short-circuit: return the rejection message with shield usage tracked
            state = GraphAgentState(usage=ctx.usage)
            return AgentRunResult(output=self.invalid_question_response, _state=state)

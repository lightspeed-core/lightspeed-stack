"""Generation settings for an agent, from a Responses request (LCORE-4716).

The Responses rewrite runs ``/v1/responses`` on a pydantic-ai agent, so the
request's model-generation fields have to reach the model as pydantic-ai
``ModelSettings`` instead of an opaque request body (design:
``docs/design/inference-backend-migration/pai-responses-lcore-rewrite.md``,
section 4.7). This module holds the one mapping; pydantic-ai's model
implementation then turns the settings into the wire format of the
selected provider.

In scope: ``temperature``, ``max_output_tokens``, ``parallel_tool_calls``
and ``reasoning``. ``top_p`` joins when the internal params model carries
it. Everything else on the request (tools, ``tool_choice``, input,
instructions, ``text.format``, conversation and continuation ids, store,
stream, metadata, LCORE-only flags) is agent, history or output
configuration and is mapped elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, Optional

from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from pydantic_ai.settings import ThinkingLevel

from log import get_logger
from models.common.responses.responses_api_params import ResponsesApiParams

logger = get_logger(__name__)

REASONING_EFFORT_OFF: Final[str] = "none"
"""The OpenResponses effort that turns reasoning off; ``thinking=False`` in pydantic-ai."""

ReasoningSummary = Literal["auto", "concise", "detailed"]


@dataclass
class GenerationSettings:
    """Model-generation settings a request asked for.

    A ``None`` field was not requested and leaves the model's default in
    place.

    Attributes:
        temperature: Sampling temperature.
        max_tokens: Maximum number of output tokens.
        parallel_tool_calls: Whether the model may call several tools at once.
        thinking: Reasoning effort as pydantic-ai's unified thinking level;
            ``False`` turns reasoning off.
        reasoning_summary: Requested reasoning summary style.

    """

    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    parallel_tool_calls: Optional[bool] = None
    thinking: Optional[ThinkingLevel] = None
    reasoning_summary: Optional[ReasoningSummary] = None

    @classmethod
    def from_responses_request(cls, params: ResponsesApiParams) -> GenerationSettings:
        """Map the generation fields of a Responses request.

        Parameters:
            params: The sanitized request parameters.

        Returns:
            The settings the request asked for; omitted fields stay ``None``.

        """
        thinking: Optional[ThinkingLevel] = None
        summary: Optional[ReasoningSummary] = None
        if params.reasoning is not None:
            effort = params.reasoning.effort
            if effort is not None:
                thinking = False if effort == REASONING_EFFORT_OFF else effort
            summary = params.reasoning.summary or params.reasoning.generate_summary
        return cls(
            temperature=params.temperature,
            max_tokens=params.max_output_tokens,
            parallel_tool_calls=params.parallel_tool_calls,
            thinking=thinking,
            reasoning_summary=summary,
        )

    def as_model_settings(self) -> OpenAIResponsesModelSettings:
        """Return the requested settings as pydantic-ai model settings.

        Only requested fields are present, so the model's default applies to
        the rest. The reasoning summary is an OpenAI-family setting and is
        passed as such; models of other families ignore it.

        Returns:
            The settings to pass to the agent run. ``OpenAIResponsesModelSettings``
            is a superset of ``ModelSettings``, used so the reasoning summary
            has a typed home.

        """
        settings = OpenAIResponsesModelSettings()
        if self.temperature is not None:
            settings["temperature"] = self.temperature
        if self.max_tokens is not None:
            settings["max_tokens"] = self.max_tokens
        if self.parallel_tool_calls is not None:
            settings["parallel_tool_calls"] = self.parallel_tool_calls
        if self.thinking is not None:
            settings["thinking"] = self.thinking
        if self.reasoning_summary is not None:
            settings["openai_reasoning_summary"] = self.reasoning_summary
        return settings

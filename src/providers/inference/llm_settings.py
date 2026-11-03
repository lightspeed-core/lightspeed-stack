"""Helpers for LLM request settings and Pydantic AI run configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Optional, Self, cast

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.settings import ModelSettings, ThinkingLevel
from pydantic_ai.usage import UsageLimits

if TYPE_CHECKING:
    from models.api.requests.responses_openai import ResponsesRequest

ReasoningSummary = Literal["auto", "concise", "detailed"]
TextVerbosity = Literal["low", "medium", "high"]

_USAGE_EXCLUDE = {"max_tool_calls", "max_infer_iters"}


class LlmRunSettings(BaseModel):
    """Shared generation and loop-limit options from Responses or query requests.

    Attributes:
        max_output_tokens: Maximum tokens to generate.
        temperature: Sampling temperature.
        parallel_tool_calls: Whether parallel tool calls are allowed.
        prompt_cache_key: Provider prompt-cache key when supported.
        safety_identifier: End-user safety identifier when supported.
        thinking: Pydantic AI unified thinking or reasoning level.
        reasoning_summary: Reasoning summary mode (Responses-style).
        text_verbosity: Text verbosity (Responses-style).
        max_tool_calls: Maximum successful tool calls for the agent run.
        max_infer_iters: Maximum model requests for the agent run.

    """

    model_config = ConfigDict(extra="forbid")

    max_output_tokens: Optional[int] = Field(
        default=None, serialization_alias="max_tokens"
    )
    temperature: Optional[float] = None
    parallel_tool_calls: Optional[bool] = None
    prompt_cache_key: Optional[str] = Field(
        default=None, serialization_alias="openai_prompt_cache_key"
    )
    safety_identifier: Optional[str] = Field(
        default=None, serialization_alias="openai_user"
    )
    thinking: Optional[ThinkingLevel] = None
    reasoning_summary: Optional[ReasoningSummary] = Field(
        default=None, serialization_alias="openai_reasoning_summary"
    )
    text_verbosity: Optional[TextVerbosity] = Field(
        default=None, serialization_alias="openai_text_verbosity"
    )
    max_tool_calls: Optional[int] = None
    max_infer_iters: Optional[int] = None

    @classmethod
    def from_responses_request(cls, request: ResponsesRequest) -> Self:
        """Build run settings from an OpenResponses request.

        Args:
            request: Responses API request body.

        Returns:
            Shared LLM run settings extracted from the request.

        """
        thinking: Optional[ThinkingLevel] = None
        reasoning_summary: Optional[ReasoningSummary] = None
        if request.reasoning is not None:
            if request.reasoning.effort is not None:
                thinking = (
                    False
                    if request.reasoning.effort == "none"
                    else request.reasoning.effort
                )
            reasoning_summary = request.reasoning.summary

        text_verbosity: Optional[TextVerbosity] = None
        if request.text is not None:
            text_verbosity = request.text.verbosity

        return cls(
            max_output_tokens=request.max_output_tokens,
            temperature=request.temperature,
            parallel_tool_calls=request.parallel_tool_calls,
            prompt_cache_key=request.prompt_cache_key,
            safety_identifier=request.safety_identifier,
            thinking=thinking,
            reasoning_summary=reasoning_summary,
            text_verbosity=text_verbosity,
            max_tool_calls=request.max_tool_calls,
            max_infer_iters=request.max_infer_iters,
        )

    def to_model_settings(self) -> Optional[ModelSettings]:
        """Convert generation fields into Pydantic AI ModelSettings.

        Returns:
            ModelSettings dict, or None when no generation fields are set.

        """
        data = self.model_dump(by_alias=True, exclude_none=True, exclude=_USAGE_EXCLUDE)
        return cast(ModelSettings, data) if data else None

    def to_usage_limits(self) -> Optional[UsageLimits]:
        """Convert loop-limit fields into Pydantic AI UsageLimits.

        Returns:
            Usage limits for the agent run, or None when no loop limits are
            set. Unset fields keep Pydantic AI UsageLimits defaults.

        """
        if self.max_infer_iters is None and self.max_tool_calls is None:
            return None

        limits = UsageLimits(tool_calls_limit=self.max_tool_calls)
        if self.max_infer_iters is not None:
            limits.request_limit = self.max_infer_iters
        return limits

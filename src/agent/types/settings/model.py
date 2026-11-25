"""Model settings for an agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, cast

from pydantic_ai.settings import ModelSettings, ThinkingLevel
from pydantic_ai.usage import UsageLimits

from models.api.requests import QueryRequest, ResponsesRequest

ReasoningSummary = Literal["auto", "concise", "detailed"]
TextVerbosity = Literal["low", "medium", "high"]


@dataclass
class AgentModelSettings:  # pylint: disable=too-many-instance-attributes
    """Generation and loop-limit options for one agent run.

    Attributes:
        max_output_tokens: Maximum tokens to generate.
        temperature: Sampling temperature.
        parallel_tool_calls: Whether parallel tool calls are allowed.
        prompt_cache_key: Provider prompt-cache key when supported.
        safety_identifier: End-user safety identifier when supported.
        thinking: Pydantic AI unified thinking or reasoning level.
        reasoning_summary: Reasoning summary mode.
        text_verbosity: Text verbosity.
        max_tool_calls: Maximum successful tool calls for the agent run.
        max_infer_iters: Maximum model requests for the agent run.

    """

    max_output_tokens: Optional[int] = None
    temperature: Optional[float] = None
    parallel_tool_calls: Optional[bool] = None
    prompt_cache_key: Optional[str] = None
    safety_identifier: Optional[str] = None
    thinking: Optional[ThinkingLevel] = None
    reasoning_summary: Optional[ReasoningSummary] = None
    text_verbosity: Optional[TextVerbosity] = None
    max_tool_calls: Optional[int] = None
    max_infer_iters: Optional[int] = None

    @classmethod
    def from_query_request(
        cls, request: QueryRequest  # pylint: disable=unused-argument
    ) -> AgentModelSettings:
        """Build model settings from a query.

        A query does not set generation or loop limits. ``request`` is
        accepted so every setting is built the same way.

        Parameters:
            request: Incoming query. Model settings do not read it.

        Returns:
            Empty model settings.

        """
        return cls()

    @classmethod
    def from_responses_request(cls, request: ResponsesRequest) -> AgentModelSettings:
        """Build model settings from a Responses request.

        Parameters:
            request: Incoming Responses request. Generation fields and loop
                limits are copied. Reasoning effort ``none`` becomes
                ``thinking=False``.

        Returns:
            Model settings extracted from the request.

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
        """Convert generation fields into Pydantic AI model settings.

        Request field names are mapped onto the keys Pydantic AI sends to the
        provider. Loop limits are omitted. Unset fields are omitted, and an
        explicit ``False`` is kept.

        Returns:
            Model settings dict, or ``None`` when no generation fields are set.

        """
        data: dict[str, object] = {}
        if self.max_output_tokens is not None:
            data["max_tokens"] = self.max_output_tokens
        if self.temperature is not None:
            data["temperature"] = self.temperature
        if self.parallel_tool_calls is not None:
            data["parallel_tool_calls"] = self.parallel_tool_calls
        if self.prompt_cache_key is not None:
            data["openai_prompt_cache_key"] = self.prompt_cache_key
        if self.safety_identifier is not None:
            data["openai_user"] = self.safety_identifier
        if self.thinking is not None:
            data["thinking"] = self.thinking
        if self.reasoning_summary is not None:
            data["openai_reasoning_summary"] = self.reasoning_summary
        if self.text_verbosity is not None:
            data["openai_text_verbosity"] = self.text_verbosity
        return cast(ModelSettings, data) if data else None

    def to_usage_limits(self) -> Optional[UsageLimits]:
        """Convert loop-limit fields into Pydantic AI usage limits.

        Returns:
            Usage limits for the agent run, or ``None`` when no loop limits
            are set. Unset fields keep Pydantic AI usage-limit defaults.

        """
        if self.max_infer_iters is None and self.max_tool_calls is None:
            return None

        limits = UsageLimits(tool_calls_limit=self.max_tool_calls)
        if self.max_infer_iters is not None:
            limits.request_limit = self.max_infer_iters
        return limits

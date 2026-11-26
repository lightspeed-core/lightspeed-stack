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

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal, Optional

from pydantic_ai.models.openai import OpenAIResponsesModelSettings
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.settings import ThinkingLevel

from log import get_logger
from models.common.responses.responses_api_params import ResponsesApiParams

logger = get_logger(__name__)

REASONING_EFFORT_OFF: Final[str] = "none"
"""The OpenResponses effort that turns reasoning off; ``thinking=False`` in pydantic-ai."""

ReasoningSummary = Literal["auto", "concise", "detailed"]

THINKING_SETTINGS: Final[tuple[str, ...]] = ("thinking", "openai_reasoning_summary")
"""Settings that only mean something when the model reasons."""


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

    def model_settings_for(
        self, profile: ModelProfile, model_id: str
    ) -> OpenAIResponsesModelSettings:
        """Return the settings the selected model can honor.

        Resolves the requested settings against the model's profile and drops,
        with a warning naming the model and the setting, what the profile rules
        out: the thinking level and the reasoning summary when the model does
        not reason, turning thinking off when the model always reasons,
        ``parallel_tool_calls`` when the model has no tools, and every setting
        the OpenAI-family profile lists as unsupported. A knob the profile is
        silent about is kept, since pydantic-ai's model implementation makes
        the final call. An unsupported optional knob is never a request error.

        Parameters:
            profile: The selected model's profile, from ``Model.profile``.
            model_id: The ``provider/model`` identifier, for the warnings.

        Returns:
            The settings to pass to the agent run.

        """
        resolved = self.as_model_settings()

        def drop(names: tuple[str, ...], reason: str) -> None:
            """Remove *names* from the resolved settings, warning for each one present."""
            for name in names:
                if name in resolved:
                    logger.warning(
                        "Dropping model setting %s for %s: %s", name, model_id, reason
                    )
                    del resolved[name]  # type: ignore[misc]

        if profile.get("supports_thinking") is False:
            drop(THINKING_SETTINGS, "the model does not support reasoning")
        elif resolved.get("thinking") is False and profile.get(
            "thinking_always_enabled"
        ):
            drop(("thinking",), "the model always reasons")
        if profile.get("supports_tools") is False:
            drop(("parallel_tool_calls",), "the model does not support tools")
        unsupported = profile.get("openai_unsupported_model_settings")
        if isinstance(unsupported, Sequence):
            drop(
                tuple(str(name) for name in unsupported),
                "the model profile lists it as unsupported",
            )
        return resolved

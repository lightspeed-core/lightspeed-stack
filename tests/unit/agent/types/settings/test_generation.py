"""Unit tests for generation settings built from a Responses request (LCORE-4716)."""

import logging
from typing import Any, Optional

import pytest
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.profiles.openai import OpenAIModelProfile

from agent.types.settings import AgentSettings
from agent.types.settings.generation import GenerationSettings
from models.common.responses.responses_api_params import ResponsesApiParams


def _params(**fields: Any) -> ResponsesApiParams:
    """Build params for a plain request plus the given generation fields."""
    return ResponsesApiParams.model_validate(
        {
            "model": "openai/gpt-x",
            "input": "hi",
            "conversation": "123e4567-e89b-12d3-a456-426614174000",
            "stream": False,
            "store": True,
            **fields,
        }
    )


class TestFromResponsesRequest:
    """OpenResponses generation fields become the matching settings."""

    def test_nothing_requested_maps_to_nothing(self) -> None:
        """Omitted fields are not forced onto the settings."""
        settings = GenerationSettings.from_responses_request(_params())
        assert settings == GenerationSettings()
        assert not settings.as_model_settings()

    def test_sampling_and_limits(self) -> None:
        """temperature, max_output_tokens and parallel_tool_calls map one to one."""
        settings = GenerationSettings.from_responses_request(
            _params(temperature=0.2, max_output_tokens=512, parallel_tool_calls=False)
        )
        assert settings.as_model_settings() == {
            "temperature": 0.2,
            "max_tokens": 512,
            "parallel_tool_calls": False,
        }

    def test_zero_and_false_are_kept(self) -> None:
        """Falsy values are requests, not omissions."""
        settings = GenerationSettings.from_responses_request(
            _params(temperature=0.0, max_output_tokens=1, parallel_tool_calls=False)
        ).as_model_settings()
        assert settings.get("temperature") == 0.0
        assert settings.get("parallel_tool_calls") is False

    @pytest.mark.parametrize(
        ("effort", "thinking"),
        [
            ("minimal", "minimal"),
            ("low", "low"),
            ("medium", "medium"),
            ("high", "high"),
            ("xhigh", "xhigh"),
            ("none", False),
        ],
    )
    def test_reasoning_effort_becomes_thinking(
        self, effort: str, thinking: Any
    ) -> None:
        """The effort level is the unified thinking setting; 'none' turns it off."""
        settings = GenerationSettings.from_responses_request(
            _params(reasoning={"effort": effort})
        )
        assert settings.thinking == thinking
        assert settings.as_model_settings() == {"thinking": thinking}

    @pytest.mark.parametrize(
        ("reasoning", "summary"),
        [
            ({"summary": "concise"}, "concise"),
            ({"generate_summary": "detailed"}, "detailed"),
            ({"summary": "auto", "generate_summary": "detailed"}, "auto"),
        ],
    )
    def test_reasoning_summary(
        self, reasoning: dict[str, str], summary: Optional[str]
    ) -> None:
        """A requested summary is passed as the OpenAI reasoning summary setting."""
        settings = GenerationSettings.from_responses_request(
            _params(reasoning=reasoning)
        )
        assert settings.as_model_settings() == {"openai_reasoning_summary": summary}

    def test_reasoning_without_fields_maps_to_nothing(self) -> None:
        """An empty reasoning object requests nothing."""
        settings = GenerationSettings.from_responses_request(_params(reasoning={}))
        assert settings == GenerationSettings()

    def test_other_request_fields_are_not_settings(self) -> None:
        """Tools, text format, continuation and friends stay out of the settings."""
        settings = GenerationSettings.from_responses_request(
            _params(
                temperature=0.5,
                previous_response_id="resp_0123456789abcdef",
                max_infer_iters=3,
                max_tool_calls=2,
                text={"format": {"type": "text"}},
                instructions="be brief",
            )
        )
        assert settings.as_model_settings() == {"temperature": 0.5}


def _requested(**fields: Any) -> GenerationSettings:
    """Build the settings a request with the given generation fields asks for."""
    return GenerationSettings.from_responses_request(_params(**fields))


class TestModelSettingsForProfile:
    """The selected model's profile decides which requested settings survive."""

    def test_unknown_profile_keeps_everything(self) -> None:
        """A profile that says nothing about a knob leaves it alone."""
        requested = _requested(
            temperature=0.3, parallel_tool_calls=True, reasoning={"effort": "low"}
        )
        assert (
            requested.model_settings_for(ModelProfile(), "openai/gpt-x")
            == requested.as_model_settings()
        )

    def test_thinking_is_dropped_when_the_model_cannot_think(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Reasoning effort and summary go together when thinking is unsupported."""
        requested = _requested(
            temperature=0.3, reasoning={"effort": "high", "summary": "auto"}
        )
        with caplog.at_level(logging.WARNING):
            resolved = requested.model_settings_for(
                ModelProfile(supports_thinking=False), "openai/gpt-x"
            )
        assert resolved == {"temperature": 0.3}
        assert "thinking" in caplog.text
        assert "openai/gpt-x" in caplog.text

    def test_turning_thinking_off_on_an_always_on_model_is_dropped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """effort 'none' cannot be honored by a model that always reasons."""
        requested = _requested(reasoning={"effort": "none"})
        with caplog.at_level(logging.WARNING):
            resolved = requested.model_settings_for(
                ModelProfile(supports_thinking=True, thinking_always_enabled=True),
                "openai/o-x",
            )
        assert not resolved
        assert "always" in caplog.text

    def test_parallel_tool_calls_dropped_without_tools(self) -> None:
        """A model without tool support has no parallel tool calls to configure."""
        requested = _requested(parallel_tool_calls=False, temperature=0.1)
        resolved = requested.model_settings_for(
            ModelProfile(supports_tools=False), "openai/gpt-x"
        )
        assert resolved == {"temperature": 0.1}

    def test_profile_unsupported_settings_are_dropped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Knobs the OpenAI-family profile lists as unsupported go, one warning each."""
        requested = _requested(
            temperature=0.3, max_output_tokens=100, parallel_tool_calls=True
        )
        profile = OpenAIModelProfile(
            openai_unsupported_model_settings=("temperature", "parallel_tool_calls")
        )
        with caplog.at_level(logging.WARNING):
            resolved = requested.model_settings_for(profile, "cerebras/llama")
        assert resolved == {"max_tokens": 100}
        assert caplog.text.count("cerebras/llama") == 2

    def test_requested_settings_are_not_mutated(self) -> None:
        """Resolution does not change what the request asked for."""
        requested = _requested(reasoning={"effort": "low"})
        requested.model_settings_for(ModelProfile(supports_thinking=False), "m")
        assert requested.thinking == "low"


def test_agent_settings_default_to_no_generation_settings() -> None:
    """A query brings no generation settings, so the model's defaults apply."""
    assert AgentSettings().generation == GenerationSettings()
    assert not AgentSettings().generation.as_model_settings()

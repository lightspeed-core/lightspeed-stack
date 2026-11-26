"""Unit tests for generation settings built from a Responses request (LCORE-4716)."""

from typing import Any, Optional

import pytest

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

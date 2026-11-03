"""Unit tests for shared LLM settings mapping."""

from ogx_api.openai_responses import (
    OpenAIResponseReasoning as Reasoning,
)
from ogx_api.openai_responses import (
    OpenAIResponseText as Text,
)
from pydantic_ai.usage import UsageLimits

from models.api.requests.responses_openai import ResponsesRequest
from providers.inference.llm_settings import LlmRunSettings


def test_to_model_settings_maps_generation_fields() -> None:
    """Generation knobs map onto unified and OpenAI-prefixed ModelSettings."""
    settings = LlmRunSettings(
        max_output_tokens=128,
        temperature=0.4,
        parallel_tool_calls=False,
        prompt_cache_key="cache-1",
        safety_identifier="user-1",
        thinking="low",
        reasoning_summary="concise",
        text_verbosity="medium",
        max_tool_calls=3,
        max_infer_iters=5,
    )

    assert settings.to_model_settings() == {
        "max_tokens": 128,
        "temperature": 0.4,
        "parallel_tool_calls": False,
        "openai_prompt_cache_key": "cache-1",
        "openai_user": "user-1",
        "thinking": "low",
        "openai_reasoning_summary": "concise",
        "openai_text_verbosity": "medium",
    }


def test_to_model_settings_omits_none_and_keeps_false() -> None:
    """Dump drops unset fields but keeps explicit False values."""
    settings = LlmRunSettings(temperature=0.2, parallel_tool_calls=False)

    assert settings.to_model_settings() == {
        "temperature": 0.2,
        "parallel_tool_calls": False,
    }


def test_to_model_settings_applies_each_serialization_alias() -> None:
    """Each aliased field dumps under its ModelSettings key alone."""
    assert LlmRunSettings(max_output_tokens=10).to_model_settings() == {
        "max_tokens": 10
    }
    assert LlmRunSettings(prompt_cache_key="ck").to_model_settings() == {
        "openai_prompt_cache_key": "ck"
    }
    assert LlmRunSettings(safety_identifier="sid").to_model_settings() == {
        "openai_user": "sid"
    }
    assert LlmRunSettings(reasoning_summary="auto").to_model_settings() == {
        "openai_reasoning_summary": "auto"
    }
    assert LlmRunSettings(text_verbosity="high").to_model_settings() == {
        "openai_text_verbosity": "high"
    }


def test_from_responses_maps_reasoning_none_to_thinking_false() -> None:
    """Effort none becomes PAI thinking=False in the factory."""
    request = ResponsesRequest(
        input="hello",
        reasoning=Reasoning(effort="none"),
    )

    assert LlmRunSettings.from_responses_request(request).thinking is False


def test_to_model_settings_returns_none_when_only_usage_fields() -> None:
    """Usage-only settings yield None rather than an empty ModelSettings dict."""
    assert LlmRunSettings(max_tool_calls=2).to_model_settings() is None


def test_to_usage_limits_maps_loop_caps() -> None:
    """Loop limits map onto UsageLimits request and tool-call caps."""
    settings = LlmRunSettings(max_infer_iters=7, max_tool_calls=4)

    assert settings.to_usage_limits() == UsageLimits(
        request_limit=7, tool_calls_limit=4
    )


def test_to_usage_limits_preserves_default_request_limit() -> None:
    """Only max_tool_calls keeps PAI's default request_limit."""
    limits = LlmRunSettings(max_tool_calls=2).to_usage_limits()

    assert limits is not None
    assert limits.tool_calls_limit == 2
    assert limits.request_limit == 50


def test_to_usage_limits_maps_infer_iters_only() -> None:
    """Only max_infer_iters sets request_limit and leaves tool_calls_limit unset."""
    limits = LlmRunSettings(max_infer_iters=3).to_usage_limits()

    assert limits == UsageLimits(request_limit=3, tool_calls_limit=None)


def test_to_usage_limits_returns_none_when_empty() -> None:
    """No loop limits yields None."""
    assert LlmRunSettings(temperature=0.1).to_usage_limits() is None


def test_from_responses_request_minimal_request() -> None:
    """A bare Responses request yields empty optional generation fields."""
    settings = LlmRunSettings.from_responses_request(ResponsesRequest(input="hello"))

    assert settings == LlmRunSettings()
    assert settings.to_model_settings() is None
    assert settings.to_usage_limits() is None


def test_from_responses_request_extracts_mapped_fields_only() -> None:
    """Responses extraction keeps MS/usage fields and drops agent-only ones."""
    request = ResponsesRequest(
        input="hello",
        max_output_tokens=64,
        temperature=0.5,
        parallel_tool_calls=True,
        prompt_cache_key="ck",
        safety_identifier="sid",
        reasoning=Reasoning(effort="high", summary="detailed"),
        text=Text(verbosity="low"),
        max_tool_calls=9,
        max_infer_iters=8,
        store=False,
        stream=True,
        instructions="system",
        tools=[],
    )

    assert LlmRunSettings.from_responses_request(request) == LlmRunSettings(
        max_output_tokens=64,
        temperature=0.5,
        parallel_tool_calls=True,
        prompt_cache_key="ck",
        safety_identifier="sid",
        thinking="high",
        reasoning_summary="detailed",
        text_verbosity="low",
        max_tool_calls=9,
        max_infer_iters=8,
    )


def test_from_responses_request_uses_reasoning_summary() -> None:
    """Reasoning summary is taken from the non-deprecated summary field."""
    request = ResponsesRequest(
        input="hello",
        reasoning=Reasoning(summary="auto"),
    )

    assert LlmRunSettings.from_responses_request(request).reasoning_summary == "auto"

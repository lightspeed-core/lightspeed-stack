"""Unit tests for model settings built from a query or Responses request."""

from ogx_api.openai_responses import (
    OpenAIResponseReasoning as Reasoning,
)
from ogx_api.openai_responses import (
    OpenAIResponseText as Text,
)
from pydantic_ai.usage import UsageLimits

from agent.types.settings.model import AgentModelSettings
from models.api.requests import QueryRequest, ResponsesRequest


def test_from_query_request_returns_empty_settings() -> None:
    """A query does not set generation or loop limits."""
    request = QueryRequest(query="What is Kubernetes?")

    assert AgentModelSettings.from_query_request(request) == AgentModelSettings()


def test_from_responses_request_minimal_request() -> None:
    """A bare Responses request yields empty optional fields."""
    settings = AgentModelSettings.from_responses_request(
        ResponsesRequest(input="hello")
    )

    assert settings == AgentModelSettings()
    assert settings.to_model_settings() is None
    assert settings.to_usage_limits() is None


def test_from_responses_request_maps_generation_fields() -> None:
    """Generation knobs are stored and dumped under Pydantic AI keys."""
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
    )

    settings = AgentModelSettings.from_responses_request(request)

    assert settings == AgentModelSettings(
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
    assert settings.to_model_settings() == {
        "max_tokens": 64,
        "temperature": 0.5,
        "parallel_tool_calls": True,
        "openai_prompt_cache_key": "ck",
        "openai_user": "sid",
        "thinking": "high",
        "openai_reasoning_summary": "detailed",
        "openai_text_verbosity": "low",
    }


def test_from_responses_request_maps_reasoning_none_to_thinking_false() -> None:
    """Effort none becomes Pydantic AI thinking=False."""
    request = ResponsesRequest(
        input="hello",
        reasoning=Reasoning(effort="none"),
    )

    settings = AgentModelSettings.from_responses_request(request)

    assert settings.thinking is False
    assert settings.to_model_settings() == {"thinking": False}


def test_to_model_settings_keeps_explicit_false() -> None:
    """An explicit false parallel-tool-calls flag is preserved."""
    settings = AgentModelSettings(temperature=0.2, parallel_tool_calls=False)

    assert settings.to_model_settings() == {
        "temperature": 0.2,
        "parallel_tool_calls": False,
    }


def test_to_model_settings_omits_loop_limits() -> None:
    """Loop limits are usage caps, not model settings."""
    settings = AgentModelSettings(max_tool_calls=2, max_infer_iters=4)

    assert settings.to_model_settings() is None


def test_to_model_settings_applies_each_provider_key() -> None:
    """Each renamed field is emitted under its Pydantic AI key alone."""
    assert AgentModelSettings(max_output_tokens=10).to_model_settings() == {
        "max_tokens": 10
    }
    assert AgentModelSettings(prompt_cache_key="ck").to_model_settings() == {
        "openai_prompt_cache_key": "ck"
    }
    assert AgentModelSettings(safety_identifier="sid").to_model_settings() == {
        "openai_user": "sid"
    }
    assert AgentModelSettings(reasoning_summary="auto").to_model_settings() == {
        "openai_reasoning_summary": "auto"
    }
    assert AgentModelSettings(text_verbosity="high").to_model_settings() == {
        "openai_text_verbosity": "high"
    }


def test_from_responses_request_uses_reasoning_summary() -> None:
    """Reasoning summary is taken from the summary field."""
    request = ResponsesRequest(
        input="hello",
        reasoning=Reasoning(summary="auto"),
    )

    settings = AgentModelSettings.from_responses_request(request)

    assert settings.reasoning_summary == "auto"
    assert settings.to_model_settings() == {"openai_reasoning_summary": "auto"}


def test_to_usage_limits_maps_loop_caps() -> None:
    """Loop limits map onto usage-limit request and tool-call caps."""
    settings = AgentModelSettings(max_infer_iters=7, max_tool_calls=4)

    assert settings.to_usage_limits() == UsageLimits(
        request_limit=7, tool_calls_limit=4
    )


def test_to_usage_limits_preserves_default_request_limit() -> None:
    """Only max_tool_calls keeps the default request limit."""
    limits = AgentModelSettings(max_tool_calls=2).to_usage_limits()

    assert limits is not None
    assert limits.tool_calls_limit == 2
    assert limits.request_limit == 50


def test_to_usage_limits_maps_infer_iters_only() -> None:
    """Only max_infer_iters sets request_limit and leaves tool_calls_limit unset."""
    limits = AgentModelSettings(max_infer_iters=3).to_usage_limits()

    assert limits == UsageLimits(request_limit=3, tool_calls_limit=None)


def test_to_usage_limits_returns_none_when_empty() -> None:
    """No loop limits yields None."""
    assert AgentModelSettings(temperature=0.1).to_usage_limits() is None

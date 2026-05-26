"""Unit tests for pydantic-ai streaming entry points."""

import pytest
from pydantic_ai.usage import RunUsage
from pytest_mock import MockerFixture

from models.common.responses.responses_api_params import ResponsesApiParams
from utils.streaming.pydantic_ai_streaming import (
    build_agent_from_responses_params,
    extract_agent_token_usage,
)


def test_build_agent_from_responses_params_not_implemented(
    mocker: MockerFixture,
) -> None:
    """Agent construction is a separate follow-up task."""
    context = mocker.Mock()
    params = ResponsesApiParams(
        input="hello",
        model="openai/gpt-4",
        conversation="conv-id",
        store=False,
        stream=True,
    )
    with pytest.raises(NotImplementedError, match="not implemented yet"):
        build_agent_from_responses_params(params, context)


class TestExtractPydanticAiTokenUsage:
    """Tests for extract_pydantic_ai_token_usage."""

    @pytest.mark.parametrize(
        "input_tokens,output_tokens,requests",
        [(100, 50, 2), (200, 100, 1)],
        ids=["usage_100_50_2req", "usage_200_100_1req"],
    )
    def test_extract_pydantic_ai_token_usage_with_usage(
        self,
        mocker: MockerFixture,
        input_tokens: int,
        output_tokens: int,
        requests: int,
    ) -> None:
        """Test extracting token usage from a pydantic-ai RunUsage object."""
        usage = RunUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            requests=requests,
        )
        mocker.patch(
            "utils.streaming.pydantic_ai_streaming.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mock_token_usage = mocker.patch(
            "utils.streaming.pydantic_ai_streaming.recording.record_llm_token_usage"
        )
        mock_llm_call = mocker.patch(
            "utils.streaming.pydantic_ai_streaming.recording.record_llm_call"
        )

        result = extract_agent_token_usage(usage, "provider1/model1", "/test-endpoint")
        assert result.input_tokens == input_tokens
        assert result.output_tokens == output_tokens
        assert result.llm_calls == requests
        mock_token_usage.assert_called_once_with(
            "provider1", "model1", input_tokens, output_tokens, "/test-endpoint"
        )
        mock_llm_call.assert_called_once_with("provider1", "model1", "/test-endpoint")

    def test_extract_pydantic_ai_token_usage_no_usage(
        self, mocker: MockerFixture
    ) -> None:
        """Test extracting token usage when usage is None."""
        mocker.patch(
            "utils.streaming.pydantic_ai_streaming.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mock_llm_call = mocker.patch(
            "utils.streaming.pydantic_ai_streaming.recording.record_llm_call"
        )

        result = extract_agent_token_usage(None, "provider1/model1", "/test-endpoint")
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.llm_calls == 1
        mock_llm_call.assert_called_once_with("provider1", "model1", "/test-endpoint")

    def test_extract_pydantic_ai_token_usage_empty_run_usage(
        self, mocker: MockerFixture
    ) -> None:
        """Test extracting token usage when RunUsage has no values."""
        mocker.patch(
            "utils.streaming.pydantic_ai_streaming.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mock_llm_call = mocker.patch(
            "utils.streaming.pydantic_ai_streaming.recording.record_llm_call"
        )

        result = extract_agent_token_usage(
            RunUsage(), "provider1/model1", "/test-endpoint"
        )
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.llm_calls == 1
        mock_llm_call.assert_called_once_with("provider1", "model1", "/test-endpoint")

    def test_extract_pydantic_ai_token_usage_zero_requests(
        self, mocker: MockerFixture
    ) -> None:
        """Test llm_calls is at least 1 when requests is zero."""
        usage = RunUsage(input_tokens=10, output_tokens=5, requests=0)
        mocker.patch(
            "utils.streaming.pydantic_ai_streaming.extract_provider_and_model_from_model_id",
            return_value=("provider1", "model1"),
        )
        mocker.patch(
            "utils.streaming.pydantic_ai_streaming.recording.record_llm_token_usage"
        )
        mocker.patch("utils.streaming.pydantic_ai_streaming.recording.record_llm_call")

        result = extract_agent_token_usage(usage, "provider1/model1", "/test-endpoint")
        assert result.llm_calls == 1

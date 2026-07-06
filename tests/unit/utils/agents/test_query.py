"""Unit tests for utils.agents.query module."""

from collections.abc import Callable
from typing import Any, Optional

import pytest
from fastapi import HTTPException
from llama_stack_api.openai_responses import (
    OpenAIResponseMessage as ResponseMessage,
)
from llama_stack_client import APIConnectionError, APIStatusError
from pydantic_ai.messages import (
    FinishReason,
    ModelRequest,
    ModelResponse,
    NativeToolCallPart,
    NativeToolReturnPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.native_tools import FileSearchTool
from pydantic_ai.usage import RunUsage
from pytest_mock import MockerFixture

from constants import ENDPOINT_PATH_QUERY
from models.common.moderation import ShieldModerationBlocked, ShieldModerationPassed
from models.common.responses.responses_api_params import ResponsesApiParams
from models.common.responses.types import ResponseInput
from models.common.turn_summary import TurnSummary
from utils.agents.query import (
    AgentFinishReason,
    build_turn_summary_from_agent_run,
    extract_agent_token_usage,
    get_agent_finish_reason,
    retrieve_agent_response,
)
from utils.token_counter import TokenCounter


@pytest.fixture(name="make_agent_run_result")
def make_agent_run_result_fixture(mocker: MockerFixture) -> Callable[..., Any]:
    """Return a factory that builds mock AgentRunResult objects."""

    def _make(
        *,
        content: str = "Hello from the agent.",
        response_id: str = "response-123",
        input_tokens: int = 10,
        output_tokens: int = 5,
        finish_reason: Optional[FinishReason] = "stop",
        model_response: Optional[ModelResponse] = None,
        new_messages: Optional[list[Any]] = None,
    ) -> Any:
        if model_response is None:
            model_response = ModelResponse(
                parts=[TextPart(content=content)],
                finish_reason=finish_reason,
                provider_response_id=response_id,
            )
        messages = new_messages if new_messages is not None else [model_response]
        run_result = mocker.MagicMock()
        run_result.response = model_response
        run_result.usage = RunUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            requests=1,
        )
        run_result.new_messages.return_value = messages
        return run_result

    return _make


@pytest.fixture(name="make_responses_params")
def make_responses_params_fixture() -> Callable[..., ResponsesApiParams]:
    """Return a factory that builds ResponsesApiParams for agent query tests."""

    def _make(
        *,
        model: str = "provider1/model1",
        input_text: ResponseInput = "What is OpenShift?",
        conversation: Optional[str] = "conv_123",
    ) -> ResponsesApiParams:
        return ResponsesApiParams.model_validate(
            {
                "model": model,
                "input": input_text,
                "conversation": conversation,
                "stream": False,
                "store": True,
            }
        )

    return _make


@pytest.fixture(name="responses_params")
def responses_params_fixture(
    make_responses_params: Callable[..., ResponsesApiParams],
) -> ResponsesApiParams:
    """Default ResponsesApiParams for agent query tests."""
    return make_responses_params()


@pytest.fixture(name="blocked_moderation")
def blocked_moderation_fixture() -> ShieldModerationBlocked:
    """Blocked shield moderation result for tests."""
    return ShieldModerationBlocked(
        message="Content blocked by shield.",
        moderation_id="modr-test-456",
        refusal_response=ResponseMessage(
            role="assistant",
            content="Content blocked by shield.",
        ),
    )


@pytest.fixture(name="patch_query_configuration")
def patch_query_configuration_fixture(mocker: MockerFixture) -> None:
    """Patch query module configuration for isolated agent query tests."""
    mock_config = mocker.MagicMock()
    mock_config.skills = None
    mock_config.rag_id_mapping = {}
    mocker.patch("utils.agents.query.configuration", mock_config)


@pytest.fixture(name="patch_recording_metrics")
def patch_recording_metrics_fixture(mocker: MockerFixture) -> None:
    """Patch LLM recording helpers so token usage tests stay isolated."""
    mock_config = mocker.MagicMock()
    mock_config.skills = None
    mock_config.rag_id_mapping = {}
    mocker.patch("utils.agents.query.configuration", mock_config)
    mocker.patch(
        "utils.agents.query.extract_vector_store_ids_from_tools",
        return_value=[],
    )
    mocker.patch("utils.agents.query.recording.record_llm_token_usage")
    mocker.patch("utils.agents.query.recording.record_llm_call")


class TestGetAgentFinishReason:
    """Tests for get_agent_finish_reason."""

    def test_returns_success_for_stop(self) -> None:
        """Test a normal stop finish reason maps to SUCCESS."""
        response = ModelResponse(
            parts=[TextPart(content="done")],
            finish_reason="stop",
        )

        assert get_agent_finish_reason(response) == AgentFinishReason.SUCCESS

    def test_returns_length_finish_reason(self) -> None:
        """Test length finish reason is preserved."""
        response = ModelResponse(
            parts=[TextPart(content="truncated")],
            finish_reason="length",
        )

        assert get_agent_finish_reason(response) == AgentFinishReason.LENGTH

    def test_returns_content_filter_finish_reason(self) -> None:
        """Test content_filter finish reason is preserved."""
        response = ModelResponse(
            parts=[TextPart(content="")],
            finish_reason="content_filter",
        )

        assert get_agent_finish_reason(response) == AgentFinishReason.CONTENT_FILTER

    def test_returns_error_when_finish_reason_missing(self) -> None:
        """Test missing finish reason maps to ERROR."""
        response = ModelResponse(
            parts=[TextPart(content="partial")],
            finish_reason=None,
        )

        assert get_agent_finish_reason(response) == AgentFinishReason.ERROR

    def test_returns_cancelled_from_provider_details(self) -> None:
        """Test provider_details cancelled overrides the model finish reason."""
        response = ModelResponse(
            parts=[TextPart(content="partial")],
            finish_reason="stop",
            provider_details={"finish_reason": "cancelled"},
        )

        assert get_agent_finish_reason(response) == AgentFinishReason.CANCELLED


class TestExtractAgentTokenUsage:
    """Tests for extract_agent_token_usage."""

    def test_builds_token_counter_from_usage(
        self, patch_recording_metrics: None
    ) -> None:
        """Test token usage is mapped from RunUsage to TokenCounter."""
        usage = RunUsage(input_tokens=42, output_tokens=17, requests=2)

        counter = extract_agent_token_usage(
            usage,
            model="provider1/model1",
            endpoint_path=ENDPOINT_PATH_QUERY,
        )

        assert counter == TokenCounter(
            input_tokens=42,
            output_tokens=17,
            llm_calls=2,
        )

    def test_llm_calls_minimum_one_when_requests_zero(
        self, patch_recording_metrics: None
    ) -> None:
        """Test llm_calls is at least 1 when the agent reports zero requests."""
        usage = RunUsage(input_tokens=1, output_tokens=1, requests=0)

        counter = extract_agent_token_usage(
            usage,
            model="provider1/model1",
            endpoint_path=ENDPOINT_PATH_QUERY,
        )

        assert counter.llm_calls == 1

    def test_records_metrics(self, mocker: MockerFixture) -> None:
        """Test LLM token usage and call metrics are recorded."""
        mock_record_usage = mocker.patch(
            "utils.agents.query.recording.record_llm_token_usage"
        )
        mock_record_call = mocker.patch("utils.agents.query.recording.record_llm_call")
        usage = RunUsage(input_tokens=8, output_tokens=3, requests=1)

        extract_agent_token_usage(
            usage,
            model="my-provider/my-model",
            endpoint_path=ENDPOINT_PATH_QUERY,
        )

        mock_record_usage.assert_called_once_with(
            "my-provider",
            "my-model",
            8,
            3,
            ENDPOINT_PATH_QUERY,
        )
        mock_record_call.assert_called_once_with(
            "my-provider",
            "my-model",
            ENDPOINT_PATH_QUERY,
        )


class TestBuildTurnSummaryFromAgentRun:
    """Tests for build_turn_summary_from_agent_run."""

    def test_builds_summary_from_text_response(
        self,
        make_agent_run_result: Callable[..., Any],
        patch_recording_metrics: None,
    ) -> None:
        """Test a successful agent run produces text, tools, id, and token usage."""
        llm_text = "OpenShift is a Kubernetes distribution."
        file_search_call = NativeToolCallPart(
            tool_name=FileSearchTool.kind,
            args={"queries": ["OpenShift"]},
            tool_call_id="fs-1",
        )
        file_search_return = NativeToolReturnPart(
            tool_name=FileSearchTool.kind,
            tool_call_id="fs-1",
            content={"status": "success", "results": []},
        )
        function_call = ToolCallPart(
            tool_name="calculate",
            args={"x": 1},
            tool_call_id="fn-1",
        )
        function_return = ToolReturnPart(
            tool_name="calculate",
            content={"result": 2},
            tool_call_id="fn-1",
        )
        model_response = ModelResponse(
            parts=[
                file_search_call,
                file_search_return,
                function_call,
                TextPart(llm_text),
            ],
            finish_reason="stop",
            provider_response_id="resp-agent-1",
        )
        run_result = make_agent_run_result(
            input_tokens=20,
            output_tokens=12,
            model_response=model_response,
            new_messages=[model_response, ModelRequest(parts=[function_return])],
        )

        summary = build_turn_summary_from_agent_run(
            run_result,
            model_id="provider1/model1",
            endpoint_path=ENDPOINT_PATH_QUERY,
            vector_store_ids=[],
            rag_id_mapping={},
        )

        assert summary.llm_response == llm_text
        assert summary.id == "resp-agent-1"
        assert summary.token_usage.input_tokens == 20
        assert summary.token_usage.output_tokens == 12
        assert summary.token_usage.llm_calls == 1
        assert len(summary.tool_calls) == 2
        assert {call.name for call in summary.tool_calls} == {
            "calculate",
            "file_search",
        }
        assert len(summary.tool_results) == 2
        assert {result.type for result in summary.tool_results} == {
            "file_search_call",
            "function_call_output",
        }

    def test_raises_http_exception_on_length_finish_reason(
        self,
        make_agent_run_result: Callable[..., Any],
    ) -> None:
        """Test non-success finish reason raises HTTPException."""
        run_result = make_agent_run_result(finish_reason="length")

        with pytest.raises(HTTPException) as exc_info:
            build_turn_summary_from_agent_run(
                run_result,
                model_id="provider1/model1",
                endpoint_path=ENDPOINT_PATH_QUERY,
                vector_store_ids=[],
                rag_id_mapping={},
            )

        assert exc_info.value.status_code == 413

    def test_raises_http_exception_on_missing_finish_reason(
        self,
        make_agent_run_result: Callable[..., Any],
    ) -> None:
        """Test missing finish reason is treated as an error."""
        run_result = make_agent_run_result(
            content="partial",
            response_id="resp-error",
            finish_reason=None,
        )

        with pytest.raises(HTTPException) as exc_info:
            build_turn_summary_from_agent_run(
                run_result,
                model_id="provider1/model1",
                endpoint_path=ENDPOINT_PATH_QUERY,
                vector_store_ids=[],
                rag_id_mapping={},
            )

        assert exc_info.value.status_code == 500


class TestRetrieveAgentResponse:
    """Tests for retrieve_agent_response."""

    @pytest.mark.asyncio
    async def test_blocked_moderation_returns_refusal_summary(
        self,
        mocker: MockerFixture,
        responses_params: ResponsesApiParams,
        blocked_moderation: ShieldModerationBlocked,
    ) -> None:
        """Test blocked moderation persists refusal and returns a turn summary."""
        mock_client = mocker.AsyncMock()
        mock_append = mocker.patch(
            "utils.agents.query.append_turn_items_to_conversation",
            new=mocker.AsyncMock(),
        )

        summary = await retrieve_agent_response(
            client=mock_client,
            responses_params=responses_params,
            moderation_result=blocked_moderation,
            endpoint_path=ENDPOINT_PATH_QUERY,
        )

        mock_append.assert_awaited_once_with(
            mock_client,
            responses_params.conversation,
            responses_params.input,
            [blocked_moderation.refusal_response],
        )
        assert summary == TurnSummary(
            id="modr-test-456",
            llm_response="Content blocked by shield.",
        )

    @pytest.mark.asyncio
    async def test_success_returns_turn_summary(
        self,
        mocker: MockerFixture,
        make_agent_run_result: Callable[..., Any],
        make_responses_params: Callable[..., ResponsesApiParams],
        patch_recording_metrics: None,
    ) -> None:
        """Test a successful agent run returns a populated turn summary."""
        run_result = make_agent_run_result(
            content="Hello!",
            response_id="resp-success",
        )
        mock_agent = mocker.AsyncMock()
        mock_agent.run = mocker.AsyncMock(return_value=run_result)
        mocker.patch(
            "utils.agents.query.build_agent",
            return_value=mock_agent,
        )

        summary = await retrieve_agent_response(
            client=mocker.AsyncMock(),
            responses_params=make_responses_params(input_text="Say hello"),
            moderation_result=ShieldModerationPassed(),
            endpoint_path=ENDPOINT_PATH_QUERY,
        )

        mock_agent.run.assert_awaited_once_with("Say hello")
        assert summary.llm_response == "Hello!"
        assert summary.id == "resp-success"

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("patch_query_configuration")
    async def test_agent_connection_error_raises_http_exception(
        self,
        mocker: MockerFixture,
        responses_params: ResponsesApiParams,
    ) -> None:
        """Test Llama Stack connection errors are mapped to HTTPException."""
        mock_agent = mocker.AsyncMock()
        mock_agent.run = mocker.AsyncMock(
            side_effect=APIConnectionError(request=mocker.Mock())
        )
        mocker.patch(
            "utils.agents.query.build_agent",
            return_value=mock_agent,
        )

        with pytest.raises(HTTPException) as exc_info:
            await retrieve_agent_response(
                client=mocker.AsyncMock(),
                responses_params=responses_params,
                moderation_result=ShieldModerationPassed(),
                endpoint_path=ENDPOINT_PATH_QUERY,
            )

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("patch_query_configuration")
    async def test_api_status_error_raises_http_exception(
        self,
        mocker: MockerFixture,
        responses_params: ResponsesApiParams,
    ) -> None:
        """Test API status errors from the agent run are mapped to HTTPException."""
        mock_agent = mocker.AsyncMock()
        mock_agent.run = mocker.AsyncMock(
            side_effect=APIStatusError(
                message="quota exceeded",
                response=mocker.Mock(),
                body=None,
            )
        )
        mocker.patch(
            "utils.agents.query.build_agent",
            return_value=mock_agent,
        )
        mock_error = mocker.Mock()
        mock_error.model_dump.return_value = {
            "status_code": 429,
            "detail": {"response": "Quota exceeded", "cause": "quota exceeded"},
        }
        mocker.patch(
            "utils.agents.query.handle_known_apistatus_errors",
            return_value=mock_error,
        )

        with pytest.raises(HTTPException) as exc_info:
            await retrieve_agent_response(
                client=mocker.AsyncMock(),
                responses_params=responses_params,
                moderation_result=ShieldModerationPassed(),
                endpoint_path=ENDPOINT_PATH_QUERY,
            )

        assert exc_info.value.status_code == 429

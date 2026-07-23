"""Unit tests for pydantic_ai_lightspeed.llamastack._model module."""

# pylint: disable=protected-access,too-few-public-methods

from collections.abc import AsyncIterator
from typing import Any

import pytest
from openai.types import responses
from pydantic_ai import ModelMessage, UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models.openai import (
    OpenAIResponsesModel,
    OpenAIResponsesModelSettings,
    OpenAIResponsesStreamedResponse,
)
from pydantic_ai.settings import ModelSettings
from pytest_mock import MockerFixture

from models.common.responses.responses_api_params import ResponsesApiParams
from pydantic_ai_lightspeed.llamastack._model import (
    _LLS_RESPONSES_EXTRA_FIELDS,
    OgxResponsesModel,
    _FilteredResponseStream,
    _model_settings_from_responses_params,
)

_REQUIRED_PARAMS = {
    "input": "hello",
    "model": "provider/model",
    "conversation": "conv-1",
    "store": True,
    "stream": True,
}


def _make_params(**overrides: object) -> ResponsesApiParams:
    """Build a ``ResponsesApiParams`` with required fields plus overrides."""
    return ResponsesApiParams(**{**_REQUIRED_PARAMS, **overrides})


class TestModelSettingsFromResponsesParams:
    """Tests for _model_settings_from_responses_params field mapping."""

    def test_store_maps_to_openai_store(self) -> None:
        """Test that store maps to openai_store."""
        params = _make_params(store=True)
        settings = _model_settings_from_responses_params(params)
        assert "openai_store" in settings
        assert settings["openai_store"] is True

    def test_max_output_tokens_maps_to_max_tokens(self) -> None:
        """Test that max_output_tokens maps to max_tokens."""
        params = _make_params(max_output_tokens=512)
        settings = _model_settings_from_responses_params(params)
        assert "max_tokens" in settings
        assert settings["max_tokens"] == 512

    def test_temperature(self) -> None:
        """Test that temperature is passed through."""
        params = _make_params(temperature=0.7)
        settings = _model_settings_from_responses_params(params)
        assert "temperature" in settings
        assert settings["temperature"] == 0.7

    def test_parallel_tool_calls(self) -> None:
        """Test that parallel_tool_calls is passed through."""
        params = _make_params(parallel_tool_calls=True)
        settings = _model_settings_from_responses_params(params)
        assert "parallel_tool_calls" in settings
        assert settings["parallel_tool_calls"] is True

    def test_extra_headers(self) -> None:
        """Test that extra_headers is converted to a dict."""
        params = _make_params(extra_headers={"X-Custom": "value"})
        settings = _model_settings_from_responses_params(params)
        assert "extra_headers" in settings
        assert settings["extra_headers"] == {"X-Custom": "value"}

    def test_previous_response_id_maps_to_openai_previous_response_id(self) -> None:
        """Test that previous_response_id maps to openai_previous_response_id."""
        params = _make_params(previous_response_id="resp-42")
        settings = _model_settings_from_responses_params(params)
        assert "openai_previous_response_id" in settings
        assert settings["openai_previous_response_id"] == "resp-42"

    def test_extra_body_fields(self) -> None:
        """Test that fields in _LLS_RESPONSES_EXTRA_FIELDS land in extra_body."""
        params = _make_params(
            max_infer_iters=5,
            max_tool_calls=10,
        )
        settings = _model_settings_from_responses_params(params)

        assert "extra_body" in settings
        assert isinstance(settings["extra_body"], dict)
        assert settings["extra_body"]["max_infer_iters"] == 5
        assert settings["extra_body"]["max_tool_calls"] == 10
        assert settings["extra_body"]["conversation"] == "conv-1"

    def test_tools_maps_to_openai_native_tools(self) -> None:
        """Test that tools maps to openai_native_tools, not extra_body."""
        tools = [{"type": "function", "name": "test-function", "parameters": {}}]
        params = _make_params(tools=tools)
        settings = _model_settings_from_responses_params(params)

        assert "openai_native_tools" in settings
        assert settings["openai_native_tools"] is params.tools
        extra_body = settings.get("extra_body", {})
        assert isinstance(extra_body, dict)
        assert "tools" not in extra_body

    def test_none_fields_excluded(self) -> None:
        """Test that None optional fields do not appear in the result."""
        params = _make_params()
        settings = _model_settings_from_responses_params(params)
        assert "max_tokens" not in settings
        assert "temperature" not in settings
        assert "parallel_tool_calls" not in settings
        assert "extra_headers" not in settings
        assert "openai_previous_response_id" not in settings


class TestFromOgxClient:
    """Tests for OgxResponsesModel.from_ogx_client factory."""

    def test_with_responses_params(self, mocker: MockerFixture) -> None:
        """Test that responses_params is converted and forwarded."""
        mock_provider = mocker.Mock()
        mocker.patch(
            "pydantic_ai_lightspeed.llamastack._model.OgxProvider.from_ogx_client",
            return_value=mock_provider,
        )
        mock_init = mocker.patch.object(
            OgxResponsesModel, "__init__", return_value=None
        )

        params = _make_params(temperature=0.5)
        client = mocker.Mock()
        result = OgxResponsesModel.from_ogx_client(
            "test-model", client, responses_params=params
        )
        assert isinstance(result, OgxResponsesModel)
        args, kwargs = mock_init.call_args
        assert kwargs["settings"]["temperature"] == 0.5
        assert kwargs["provider"] is mock_provider
        assert kwargs["profile"] is None
        assert args[0] == "test-model"

    def test_with_model_settings(self, mocker: MockerFixture) -> None:
        """Test that model_settings is forwarded directly."""
        mock_provider = mocker.Mock()
        mocker.patch(
            "pydantic_ai_lightspeed.llamastack._model.OgxProvider.from_ogx_client",
            return_value=mock_provider,
        )
        mock_init = mocker.patch.object(
            OgxResponsesModel, "__init__", return_value=None
        )

        settings: ModelSettings = {"temperature": 0.9}
        client = mocker.Mock()
        result = OgxResponsesModel.from_ogx_client(
            "test-model", client, model_settings=settings
        )

        assert isinstance(result, OgxResponsesModel)
        args, kwargs = mock_init.call_args
        assert kwargs["settings"] is settings
        assert kwargs["provider"] is mock_provider
        assert kwargs["profile"] is None
        assert args[0] == "test-model"

    def test_with_neither(self, mocker: MockerFixture) -> None:
        """Test that settings is None when neither param is provided."""
        mock_provider = mocker.Mock()
        mocker.patch(
            "pydantic_ai_lightspeed.llamastack._model.OgxProvider.from_ogx_client",
            return_value=mock_provider,
        )
        mock_init = mocker.patch.object(
            OgxResponsesModel, "__init__", return_value=None
        )

        client = mocker.Mock()
        result = OgxResponsesModel.from_ogx_client("test-model", client)

        assert isinstance(result, OgxResponsesModel)
        args, kwargs = mock_init.call_args
        assert kwargs["settings"] is None
        assert kwargs["provider"] is mock_provider
        assert kwargs["profile"] is None
        assert args[0] == "test-model"

    def test_both_raises_value_error(self, mocker: MockerFixture) -> None:
        """Test that providing both raises ValueError."""
        mocker.patch(
            "pydantic_ai_lightspeed.llamastack._model.OgxProvider.from_ogx_client",
            return_value=mocker.Mock(),
        )

        params = _make_params()
        settings: ModelSettings = {"temperature": 0.5}
        client = mocker.Mock()

        with pytest.raises(ValueError, match="ResponsesApiParams or ModelSetting"):
            OgxResponsesModel.from_ogx_client(
                "test-model",
                client,
                responses_params=params,
                model_settings=settings,
            )


class TestPrepareConversationContinuation:
    """Tests for OgxResponsesModel._prepare_conversation_continuation."""

    @pytest.fixture(name="model")
    def model_fixture(self, mocker: MockerFixture) -> OgxResponsesModel:
        """Create a OgxResponsesModel with mocked __init__."""
        mocker.patch.object(OgxResponsesModel, "__init__", return_value=None)
        return OgxResponsesModel("test-model")

    def test_none_settings_returns_unchanged(
        self, model: OgxResponsesModel, mocker: MockerFixture
    ) -> None:
        """Test that None model_settings returns messages and settings unchanged."""
        messages = [mocker.Mock()]
        result_msgs, result_settings = model._prepare_conversation_continuation(
            messages, None
        )
        assert result_msgs is messages
        assert result_settings is None

    def test_empty_settings_returns_unchanged(self, model: OgxResponsesModel) -> None:
        """Test that empty dict model_settings returns unchanged."""
        messages: list = []
        settings: ModelSettings = {}
        result_msgs, result_settings = model._prepare_conversation_continuation(
            messages, settings
        )
        assert result_msgs is messages
        assert result_settings is settings

    def test_no_extra_body_returns_unchanged(
        self, model: OgxResponsesModel, mocker: MockerFixture
    ) -> None:
        """Test that settings without extra_body returns unchanged."""
        messages = [mocker.Mock()]
        settings: ModelSettings = {"temperature": 0.5}
        result_msgs, result_settings = model._prepare_conversation_continuation(
            messages, settings
        )
        assert result_msgs is messages
        assert result_settings is settings

    def test_extra_body_without_conversation_returns_unchanged(
        self, model: OgxResponsesModel, mocker: MockerFixture
    ) -> None:
        """Test that extra_body without 'conversation' key returns unchanged."""
        messages = [mocker.Mock()]
        settings: ModelSettings = {"extra_body": {"max_infer_iters": 5}}
        result_msgs, result_settings = model._prepare_conversation_continuation(
            messages, settings
        )
        assert result_msgs is messages
        assert result_settings is settings

    def test_no_model_response_returns_unchanged(
        self, model: OgxResponsesModel, mocker: MockerFixture
    ) -> None:
        """Test that messages without ModelResponse returns unchanged."""
        messages = [mocker.Mock(), mocker.Mock()]
        settings: ModelSettings = {"extra_body": {"conversation": "conv-1"}}
        result_msgs, result_settings = model._prepare_conversation_continuation(
            messages, settings
        )
        assert result_msgs is messages
        assert result_settings is settings

    def test_model_response_without_provider_id_returns_unchanged(
        self, model: OgxResponsesModel
    ) -> None:
        """Test that ModelResponse without provider_response_id is ignored."""
        response_msg = ModelResponse(parts=[], provider_response_id=None)
        messages: list[ModelMessage] = [response_msg]
        settings: ModelSettings = {"extra_body": {"conversation": "conv-1"}}
        result_msgs, result_settings = model._prepare_conversation_continuation(
            messages, settings
        )
        assert result_msgs is messages
        assert result_settings is settings

    def test_trims_messages_and_strips_previous_response_id(
        self, model: OgxResponsesModel, mocker: MockerFixture
    ) -> None:
        """Test that messages are trimmed and previous_response_id is removed."""
        msg_before = mocker.Mock()
        response_msg = ModelResponse(parts=[], provider_response_id="resp-1")
        msg_after = mocker.Mock()
        messages = [msg_before, response_msg, msg_after]
        settings: OpenAIResponsesModelSettings = {
            "extra_body": {"conversation": "conv-1"},
            "openai_previous_response_id": "resp-1",
        }
        result_msgs, result_settings = model._prepare_conversation_continuation(
            messages, settings
        )
        assert result_msgs == [msg_after]
        assert result_settings is not None
        assert "openai_previous_response_id" not in result_settings
        assert "extra_body" in result_settings
        assert result_settings["extra_body"] == {"conversation": "conv-1"}

    def test_trims_without_previous_response_id_in_settings(
        self, model: OgxResponsesModel, mocker: MockerFixture
    ) -> None:
        """Test trimming works when settings lacks previous_response_id."""
        response_msg = ModelResponse(parts=[], provider_response_id="resp-1")
        msg_after = mocker.Mock()
        messages = [response_msg, msg_after]
        settings: ModelSettings = {"extra_body": {"conversation": "conv-1"}}
        result_msgs, result_settings = model._prepare_conversation_continuation(
            messages, settings
        )
        assert result_msgs == [msg_after]
        assert result_settings is not None
        assert "openai_previous_response_id" not in result_settings

    def test_uses_last_model_response_when_multiple(
        self, model: OgxResponsesModel, mocker: MockerFixture
    ) -> None:
        """Test that the last ModelResponse with provider_response_id is used."""
        msg1 = mocker.Mock()
        resp1 = ModelResponse(parts=[], provider_response_id="resp-1")
        msg2 = mocker.Mock()
        resp2 = ModelResponse(parts=[], provider_response_id="resp-2")
        msg3 = mocker.Mock()
        messages = [msg1, resp1, msg2, resp2, msg3]
        settings: OpenAIResponsesModelSettings = {
            "extra_body": {"conversation": "conv-1"},
            "openai_previous_response_id": "resp-2",
        }
        result_msgs, result_settings = model._prepare_conversation_continuation(
            messages, settings
        )
        assert result_msgs == [msg3]
        assert result_settings is not None
        assert "openai_previous_response_id" not in result_settings

    def test_only_skip_model_response_with_provider_response_id(
        self, model: OgxResponsesModel, mocker: MockerFixture
    ) -> None:
        """Test that the last ModelResponse with provider_response_id is used."""
        msg1 = mocker.Mock()
        resp1 = ModelResponse(parts=[], provider_response_id="resp-1")
        msg2 = mocker.Mock()
        resp2 = ModelResponse(parts=[])
        msg3 = mocker.Mock()
        messages = [msg1, resp1, msg2, resp2, msg3]
        settings: OpenAIResponsesModelSettings = {
            "extra_body": {"conversation": "conv-1"},
            "openai_previous_response_id": "resp-2",
        }
        result_msgs, result_settings = model._prepare_conversation_continuation(
            messages, settings
        )
        assert result_msgs == [msg2, resp2, msg3]
        assert result_settings is not None
        assert "openai_previous_response_id" not in result_settings

    def test_does_not_mutate_original_settings(
        self, model: OgxResponsesModel, mocker: MockerFixture
    ) -> None:
        """Test that the original settings dict is not modified."""
        response_msg = ModelResponse(parts=[], provider_response_id="resp-1")
        messages = [response_msg, mocker.Mock()]
        settings: OpenAIResponsesModelSettings = {
            "extra_body": {"conversation": "conv-1"},
            "openai_previous_response_id": "resp-1",
        }
        model._prepare_conversation_continuation(messages, settings)
        assert "openai_previous_response_id" in settings


class TestRequest:
    """Tests for OgxResponsesModel.request."""

    @pytest.mark.asyncio
    async def test_calls_prepare_and_delegates_to_super(
        self, mocker: MockerFixture
    ) -> None:
        """Test that request calls _prepare_conversation_continuation and delegates."""
        mocker.patch.object(OgxResponsesModel, "__init__", return_value=None)
        model = OgxResponsesModel("test-model")

        original_msgs = [mocker.Mock()]
        original_settings: OpenAIResponsesModelSettings = {
            "temperature": 0.3,
            "openai_previous_response_id": "resp-1",
        }
        prepared_msgs = [mocker.Mock()]
        prepared_settings: OpenAIResponsesModelSettings = {"temperature": 0.3}

        mock_prepare = mocker.patch.object(
            model,
            "_prepare_conversation_continuation",
            return_value=(prepared_msgs, prepared_settings),
        )

        expected_result = mocker.Mock()
        mock_super_request = mocker.patch.object(
            OpenAIResponsesModel,
            "request",
            new_callable=mocker.AsyncMock,
            return_value=expected_result,
        )

        mock_params = mocker.Mock()
        result = await model.request(original_msgs, original_settings, mock_params)

        mock_prepare.assert_called_once_with(original_msgs, original_settings)
        mock_super_request.assert_called_once()
        args, _ = mock_super_request.call_args
        assert args[0] is prepared_msgs
        assert args[1] is prepared_settings
        assert args[2] is mock_params
        assert result is expected_result


def _make_mock_response_stream(mocker: MockerFixture, events: list[Any]) -> Any:
    """Create a mock AsyncStream that yields given events and supports async with."""
    mock = mocker.Mock()
    mock.__aiter__ = lambda _: _async_iter(events)
    mock.__aenter__ = mocker.AsyncMock(return_value=mock)
    mock.__aexit__ = mocker.AsyncMock(return_value=False)
    mock.close = mocker.AsyncMock()
    return mock


def _make_response_created_event() -> responses.ResponseCreatedEvent:
    """Build a ResponseCreatedEvent for stream tests."""
    return responses.ResponseCreatedEvent(
        response=responses.Response(
            id="resp-1",
            created_at=0,
            model="test",
            object="response",
            output=[],
            parallel_tool_calls=False,
            tool_choice="auto",
            tools=[],
            status="completed",
        ),
        sequence_number=0,
        type="response.created",
    )


class TestRequestStream:
    """Tests for OgxResponsesModel.request_stream."""

    @pytest.fixture(name="model")
    def model_fixture(self, mocker: MockerFixture) -> OgxResponsesModel:
        """Create a OgxResponsesModel with stream-related attributes set."""
        mocker.patch.object(OgxResponsesModel, "__init__", return_value=None)
        model = OgxResponsesModel("test-model")
        mocker.patch.object(
            type(model),
            "model_name",
            new_callable=mocker.PropertyMock,
            return_value="test-model",
        )
        model._provider = mocker.Mock()
        model._provider.name = "test-provider"
        model._provider.base_url = "http://localhost"
        mocker.patch(
            "pydantic_ai_lightspeed.llamastack._model.check_allow_model_requests"
        )
        return model

    @pytest.mark.asyncio
    async def test_calls_prepare_continuation(
        self, model: OgxResponsesModel, mocker: MockerFixture
    ) -> None:
        """Test that request_stream calls _prepare_conversation_continuation."""
        original_msgs = [mocker.Mock()]
        original_settings: ModelSettings = {"temperature": 0.5}

        mock_prepare = mocker.patch.object(
            model,
            "_prepare_conversation_continuation",
            return_value=(original_msgs, original_settings),
        )

        mock_stream = _make_mock_response_stream(
            mocker, [_make_response_created_event()]
        )
        model._responses_create = mocker.AsyncMock(return_value=mock_stream)
        async with model.request_stream(
            original_msgs, original_settings, mocker.Mock()
        ):
            pass

        mock_prepare.assert_called_once_with(original_msgs, original_settings)

    @pytest.mark.asyncio
    async def test_empty_stream_raises(
        self, model: OgxResponsesModel, mocker: MockerFixture
    ) -> None:
        """Test that an empty stream raises UnexpectedModelBehavior."""
        mocker.patch.object(
            model,
            "_prepare_conversation_continuation",
            return_value=([mocker.Mock()], {}),
        )

        mock_stream = _make_mock_response_stream(mocker, [])
        model._responses_create = mocker.AsyncMock(return_value=mock_stream)
        with pytest.raises(UnexpectedModelBehavior, match="ended without content"):
            async with model.request_stream([mocker.Mock()], {}, mocker.Mock()):
                pass

    @pytest.mark.asyncio
    async def test_wrong_first_event_raises(
        self, model: OgxResponsesModel, mocker: MockerFixture
    ) -> None:
        """Test that a non-ResponseCreatedEvent first event raises."""
        mocker.patch.object(
            model,
            "_prepare_conversation_continuation",
            return_value=([mocker.Mock()], {}),
        )

        wrong_event = responses.ResponseCompletedEvent(
            response=responses.Response(
                id="resp-1",
                created_at=0,
                model="test",
                object="response",
                output=[],
                parallel_tool_calls=False,
                tool_choice="auto",
                tools=[],
                status="completed",
            ),
            sequence_number=0,
            type="response.completed",
        )
        mock_stream = _make_mock_response_stream(mocker, [wrong_event])
        model._responses_create = mocker.AsyncMock(return_value=mock_stream)
        with pytest.raises(
            UnexpectedModelBehavior, match="Expected ResponseCreatedEvent"
        ):
            async with model.request_stream([mocker.Mock()], {}, mocker.Mock()):
                pass

    @pytest.mark.asyncio
    async def test_happy_path_yields_streamed_response(
        self, model: OgxResponsesModel, mocker: MockerFixture
    ) -> None:
        """Test that a valid stream yields an OpenAIResponsesStreamedResponse."""
        mocker.patch.object(
            model,
            "_prepare_conversation_continuation",
            return_value=([mocker.Mock()], {}),
        )

        mock_stream = _make_mock_response_stream(
            mocker, [_make_response_created_event()]
        )
        model._responses_create = mocker.AsyncMock(return_value=mock_stream)
        async with model.request_stream([mocker.Mock()], {}, mocker.Mock()) as streamed:
            assert isinstance(streamed, OpenAIResponsesStreamedResponse)


class TestLlsResponsesExtraFields:
    """Tests for the _LLS_RESPONSES_EXTRA_FIELDS constant."""

    def test_is_frozenset(self) -> None:
        """Test that _LLS_RESPONSES_EXTRA_FIELDS is a frozenset."""
        assert isinstance(_LLS_RESPONSES_EXTRA_FIELDS, frozenset)

    def test_contains_expected_fields(self) -> None:
        """Test that key fields are present."""
        expected = {
            "conversation",
            "max_infer_iters",
            "tool_choice",
            "include",
            "text",
            "reasoning",
            "prompt",
            "metadata",
            "max_tool_calls",
            "safety_identifier",
        }
        assert expected == _LLS_RESPONSES_EXTRA_FIELDS


def _make_delta(
    item_id: str, delta: str, output_index: int = 0, seq: int = 1
) -> responses.ResponseFunctionCallArgumentsDeltaEvent:
    """Build a ResponseFunctionCallArgumentsDeltaEvent."""
    return responses.ResponseFunctionCallArgumentsDeltaEvent(
        delta=delta,
        item_id=item_id,
        output_index=output_index,
        sequence_number=seq,
        type="response.function_call_arguments.delta",
    )


def _make_function_tool_call_added(
    item_id: str,
) -> responses.ResponseOutputItemAddedEvent:
    """Build a ResponseOutputItemAddedEvent for a ResponseFunctionToolCall."""
    item = responses.ResponseFunctionToolCall(
        id=item_id,
        call_id="call-1",
        name="my_tool",
        arguments="",
        type="function_call",
    )
    return responses.ResponseOutputItemAddedEvent(
        item=item,
        output_index=0,
        sequence_number=0,
        type="response.output_item.added",
    )


def _make_mcp_call_added(item_id: str) -> responses.ResponseOutputItemAddedEvent:
    """Build a ResponseOutputItemAddedEvent for an McpCall."""
    item = responses.response_output_item.McpCall(
        id=item_id,
        arguments="",
        name="mcp_tool",
        server_label="server",
        type="mcp_call",
    )
    return responses.ResponseOutputItemAddedEvent(
        item=item,
        output_index=0,
        sequence_number=0,
        type="response.output_item.added",
    )


async def _async_iter(events: list[Any]) -> AsyncIterator[Any]:
    """Turn a list of events into an async iterator."""
    for e in events:
        yield e


class TestFilteredResponseStream:
    """Tests for _FilteredResponseStream event reordering."""

    @pytest.mark.asyncio
    async def test_passthrough_normal_events(self, mocker: MockerFixture) -> None:
        """Test that non-tool events pass through unchanged."""
        event = responses.ResponseCompletedEvent(
            response=responses.Response(
                id="resp-1",
                created_at=0,
                model="test",
                object="response",
                output=[],
                parallel_tool_calls=False,
                tool_choice="auto",
                tools=[],
                status="completed",
            ),
            sequence_number=0,
            type="response.completed",
        )
        source = mocker.Mock()
        source.__aiter__ = lambda _: _async_iter([event])

        stream = _FilteredResponseStream(source)
        result = [e async for e in stream]

        assert result == [event]

    @pytest.mark.asyncio
    async def test_buffers_early_argument_delta(self, mocker: MockerFixture) -> None:
        """Test that a delta before its announcement is buffered and not yielded."""
        delta = _make_delta("item-1", '{"key":')
        source = mocker.Mock()
        source.__aiter__ = lambda _: _async_iter([delta])

        stream = _FilteredResponseStream(source)
        result = [e async for e in stream]

        assert result == []

    @pytest.mark.asyncio
    async def test_replays_buffered_deltas_for_function_tool_call(
        self, mocker: MockerFixture
    ) -> None:
        """Test that buffered deltas replay after a FunctionToolCall announcement."""
        delta1 = _make_delta("item-1", '{"key":', seq=1)
        delta2 = _make_delta("item-1", '"val"}', seq=2)
        announcement = _make_function_tool_call_added("item-1")

        source = mocker.Mock()
        source.__aiter__ = lambda _: _async_iter([delta1, delta2, announcement])

        stream = _FilteredResponseStream(source)
        result = [e async for e in stream]

        assert result[0] is announcement
        assert result[1] is delta1
        assert result[2] is delta2

    @pytest.mark.asyncio
    async def test_replays_mcp_buffered_deltas_with_suffixed_id(
        self, mocker: MockerFixture
    ) -> None:
        """Test that MCP deltas are combined with -call suffix on item_id."""
        delta1 = _make_delta("mcp-1", '{"arg":', seq=1)
        delta2 = _make_delta("mcp-1", '"v"}', seq=2)
        announcement = _make_mcp_call_added("mcp-1")

        source = mocker.Mock()
        source.__aiter__ = lambda _: _async_iter([delta1, delta2, announcement])

        stream = _FilteredResponseStream(source)
        result = [e async for e in stream]

        assert result[0] is announcement
        replayed = result[1]
        assert isinstance(replayed, responses.ResponseFunctionCallArgumentsDeltaEvent)
        assert replayed.item_id == "mcp-1-call"
        assert replayed.delta == '{"arg":"v"}}'

    @pytest.mark.asyncio
    async def test_no_buffered_deltas(self, mocker: MockerFixture) -> None:
        """Test that an announcement with no prior deltas yields only itself."""
        announcement = _make_function_tool_call_added("item-1")
        source = mocker.Mock()
        source.__aiter__ = lambda _: _async_iter([announcement])

        stream = _FilteredResponseStream(source)
        result = [e async for e in stream]

        assert result == [announcement]

    @pytest.mark.asyncio
    async def test_delta_after_announcement_passes_through(
        self, mocker: MockerFixture
    ) -> None:
        """Test that a delta arriving after its announcement passes through."""
        announcement = _make_function_tool_call_added("item-1")
        delta = _make_delta("item-1", '{"key":"val"}')

        source = mocker.Mock()
        source.__aiter__ = lambda _: _async_iter([announcement, delta])

        stream = _FilteredResponseStream(source)
        result = [e async for e in stream]

        assert result == [announcement, delta]

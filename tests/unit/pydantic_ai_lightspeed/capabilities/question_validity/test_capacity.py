"""Unit tests for pydantic_ai_lightspeed.capabilities.question_validity._capacity module."""

# pylint: disable=protected-access

from unittest.mock import AsyncMock

import pytest
from pydantic_ai import AgentRunResult, RunContext
from pydantic_ai.messages import ImageUrl, ModelResponse, TextContent, TextPart
from pydantic_ai.usage import RequestUsage, RunUsage
from pytest_mock import MockerFixture

from pydantic_ai_lightspeed.capabilities.question_validity._capacity import (
    DEFAULT_INVALID_QUESTION_RESPONSE,
    DEFAULT_MODEL_PROMPT,
    SUBJECT_ALLOWED,
    SUBJECT_REJECTED,
    QuestionValidity,
    _extract_message_str_from_user_content,
    _remove_conversation_from_settings,
)


class _FakeModel:
    """Minimal model stand-in that supports copy.copy like pydantic-ai Models."""

    def __init__(self, _settings: dict | None = None) -> None:
        self._settings = _settings

    @property
    def settings(self) -> dict | None:
        """Return model settings."""
        return self._settings


class TestExtractMessageStrFromUserContent:
    """Tests for _extract_message_str_from_user_content helper."""

    def test_extracts_plain_strings(self) -> None:
        """Test extraction from a sequence of plain strings."""
        content = ["hello", "world"]
        result = _extract_message_str_from_user_content(content)
        assert result == "hello\nworld"

    def test_extracts_text_content(self) -> None:
        """Test extraction from TextContent objects."""
        content = [TextContent(content="first"), TextContent(content="second")]
        result = _extract_message_str_from_user_content(content)
        assert result == "first\nsecond"

    def test_mixed_str_and_text_content(self) -> None:
        """Test extraction from a mix of strings and TextContent."""
        content = ["plain", TextContent(content="rich")]
        result = _extract_message_str_from_user_content(content)
        assert result == "plain\nrich"

    def test_empty_sequence(self) -> None:
        """Test extraction from an empty sequence."""
        result = _extract_message_str_from_user_content([])
        assert result == ""

    def test_single_string(self) -> None:
        """Test extraction from a single-element sequence."""
        result = _extract_message_str_from_user_content(["only"])
        assert result == "only"

    def test_sequence_with_non_text_content(self) -> None:
        """Test extraction from a single-element sequence."""
        result = _extract_message_str_from_user_content([ImageUrl("fake.png"), "keep"])
        assert result == "keep"


class TestRemoveConversationFromSettings:
    """Tests for _remove_conversation_from_settings helper."""

    def test_removes_conversation_key(self) -> None:
        """Test that conversation is removed from extra_body in settings."""
        model = _FakeModel(
            _settings={
                "extra_body": {"conversation": "some_conv", "other_key": "value"}
            }
        )

        result = _remove_conversation_from_settings(model)  # type: ignore[arg-type]

        assert result.settings is not None
        assert "extra_body" in result.settings
        assert result.settings["extra_body"] is not None
        assert isinstance(result.settings["extra_body"], dict)
        assert "conversation" not in result.settings["extra_body"]
        assert "other_key" in result.settings["extra_body"]
        assert result.settings["extra_body"]["other_key"] == "value"

    def test_preserves_other_extra_body_keys(self) -> None:
        """Test that non-conversation keys in extra_body are preserved."""
        model = _FakeModel(
            _settings={"extra_body": {"conversation": "conv", "key_a": 1, "key_b": 2}}
        )

        result = _remove_conversation_from_settings(model)  # type: ignore[arg-type]

        assert result.settings is not None
        assert "extra_body" in result.settings
        assert result.settings["extra_body"] is not None
        assert isinstance(result.settings["extra_body"], dict)
        assert result.settings["extra_body"] == {"key_a": 1, "key_b": 2}

    def test_no_settings(self) -> None:
        """Test with model that has no settings returns unchanged copy."""
        model = _FakeModel(_settings=None)

        result = _remove_conversation_from_settings(model)  # type: ignore[arg-type]

        assert result is model
        assert result.settings is None

    def test_no_extra_body(self) -> None:
        """Test with settings that have no extra_body key returns unchanged copy."""
        model = _FakeModel(_settings={"some_other_setting": True})

        result = _remove_conversation_from_settings(model)  # type: ignore[arg-type]

        assert result is model
        assert result.settings == {"some_other_setting": True}

    def test_no_conversation_in_extra_body(self) -> None:
        """Test with extra_body that has no conversation key returns unchanged copy."""
        model = _FakeModel(_settings={"extra_body": {"other_key": "val"}})

        result = _remove_conversation_from_settings(model)  # type: ignore[arg-type]

        assert result is model
        assert result.settings == {"extra_body": {"other_key": "val"}}

    def test_does_not_mutate_original(self) -> None:
        """Test that the original model's settings are not modified."""
        original_extra_body = {"conversation": "conv", "keep": "this"}
        model = _FakeModel(_settings={"extra_body": original_extra_body})

        _remove_conversation_from_settings(model)  # type: ignore[arg-type]

        assert "conversation" in original_extra_body


class TestQuestionValidityInit:
    """Tests for QuestionValidity dataclass initialization."""

    def test_default_model_prompt(self) -> None:
        """Test that default model_prompt is used."""
        qv = QuestionValidity(model=_FakeModel())  # type: ignore[arg-type]

        assert qv.model_prompt == DEFAULT_MODEL_PROMPT

    def test_default_invalid_question_response(self) -> None:
        """Test that default invalid_question_response is used."""
        qv = QuestionValidity(model=_FakeModel())  # type: ignore[arg-type]

        assert qv.invalid_question_response == DEFAULT_INVALID_QUESTION_RESPONSE

    def test_custom_model_prompt(self) -> None:
        """Test that custom model_prompt can be provided."""
        qv = QuestionValidity(
            model=_FakeModel(),  # type: ignore[arg-type]
            model_prompt="custom prompt ${message}",
        )

        assert qv.model_prompt == "custom prompt ${message}"

    def test_custom_invalid_response(self) -> None:
        """Test that custom invalid_question_response can be provided."""
        qv = QuestionValidity(model=_FakeModel(), invalid_question_response="Nope!")  # type: ignore[arg-type]

        assert qv.invalid_question_response == "Nope!"

    def test_post_init_removes_conversation(self) -> None:
        """Test that __post_init__ calls _remove_conversation_from_settings."""
        model = _FakeModel(
            _settings={
                "extra_body": {"conversation": "should_be_removed", "keep": "this"}
            }
        )

        qv = QuestionValidity(model=model)  # type: ignore[arg-type]

        assert qv.model.settings is not None
        assert "extra_body" in qv.model.settings
        assert isinstance(qv.model.settings["extra_body"], dict)
        assert "conversation" not in qv.model.settings["extra_body"]


class TestBuildPrompt:
    """Tests for QuestionValidity._build_prompt method."""

    @pytest.fixture(name="question_validity")
    def question_validity_fixture(self) -> QuestionValidity:
        """Create a QuestionValidity instance with a mock model."""
        return QuestionValidity(model=_FakeModel())  # type: ignore[arg-type]

    def test_string_input(self, question_validity: QuestionValidity) -> None:
        """Test prompt building with a plain string input."""
        prompt = question_validity._build_prompt("How do I scale pods?")

        assert "How do I scale pods?" in prompt
        assert SUBJECT_ALLOWED in prompt
        assert SUBJECT_REJECTED in prompt

    def test_none_input(self, question_validity: QuestionValidity) -> None:
        """Test prompt building with None input uses empty string."""
        prompt = question_validity._build_prompt(None)

        assert "Question:\n\nResponse:" in prompt

    def test_sequence_input(self, question_validity: QuestionValidity) -> None:
        """Test prompt building with a sequence of UserContent."""
        content = ["What is a", TextContent(content="deployment?")]

        prompt = question_validity._build_prompt(content)

        assert "What is a\ndeployment?" in prompt

    def test_substitutes_allowed_and_rejected(
        self, question_validity: QuestionValidity
    ) -> None:
        """Test that ALLOWED and REJECTED tokens are substituted."""
        prompt = question_validity._build_prompt("test")

        assert SUBJECT_ALLOWED in prompt
        assert SUBJECT_REJECTED in prompt
        assert "${allowed}" not in prompt
        assert "${rejected}" not in prompt
        assert "${message}" not in prompt

    def test_custom_prompt_template(self) -> None:
        """Test with a custom prompt template."""
        qv = QuestionValidity(
            model=_FakeModel(),  # type: ignore[arg-type]
            model_prompt="Is '${message}' valid? ${allowed}/${rejected}",
        )

        prompt = qv._build_prompt("my question")

        assert prompt == f"Is 'my question' valid? {SUBJECT_ALLOWED}/{SUBJECT_REJECTED}"


class TestWrapRun:
    """Tests for QuestionValidity.wrap_run method."""

    @pytest.fixture(name="mock_model")
    def mock_model_fixture(self) -> _FakeModel:
        """Create a fake model."""
        return _FakeModel()

    @pytest.fixture(name="mock_ctx")
    def mock_ctx_fixture(self, mocker: MockerFixture) -> RunContext:
        """Create a mock RunContext."""
        ctx = mocker.Mock(spec=RunContext)
        ctx.prompt = "How do I create a pod?"
        ctx.usage = RunUsage()
        return ctx

    @pytest.fixture(name="mock_handler")
    def mock_handler_fixture(self, mocker: MockerFixture) -> AsyncMock:
        """Create a mock WrapRunHandler."""
        handler = mocker.AsyncMock()
        handler.return_value = mocker.Mock(spec=AgentRunResult)
        return handler

    @pytest.mark.asyncio
    async def test_allowed_question_calls_handler(
        self,
        mocker: MockerFixture,
        mock_model: _FakeModel,
        mock_ctx: RunContext,
        mock_handler: AsyncMock,
    ) -> None:
        """Test that an allowed question proceeds to the handler."""
        mock_response = ModelResponse(
            parts=[TextPart(content=SUBJECT_ALLOWED)],
            usage=RequestUsage(input_tokens=10, output_tokens=1),
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capacity.model_request",
            return_value=mock_response,
        )

        qv = QuestionValidity(model=mock_model)  # type: ignore[arg-type]
        result = await qv.wrap_run(mock_ctx, handler=mock_handler)

        mock_handler.assert_awaited_once()
        assert result == mock_handler.return_value

    @pytest.mark.asyncio
    async def test_rejected_question_returns_rejection(
        self,
        mocker: MockerFixture,
        mock_model: _FakeModel,
        mock_ctx: RunContext,
        mock_handler: AsyncMock,
    ) -> None:
        """Test that a rejected question short-circuits with rejection message."""
        mock_response = ModelResponse(
            parts=[TextPart(content=SUBJECT_REJECTED)],
            usage=RequestUsage(input_tokens=10, output_tokens=1),
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capacity.model_request",
            return_value=mock_response,
        )

        qv = QuestionValidity(model=mock_model)  # type: ignore[arg-type]
        result = await qv.wrap_run(mock_ctx, handler=mock_handler)

        mock_handler.assert_not_awaited()
        assert isinstance(result, AgentRunResult)
        assert result.output == DEFAULT_INVALID_QUESTION_RESPONSE

    @pytest.mark.asyncio
    async def test_unexpected_response_treated_as_rejected(
        self,
        mocker: MockerFixture,
        mock_model: _FakeModel,
        mock_ctx: RunContext,
        mock_handler: AsyncMock,
    ) -> None:
        """Test that an unexpected model response is treated as rejection."""
        mock_response = ModelResponse(
            parts=[TextPart(content="I don't understand")],
            usage=RequestUsage(input_tokens=10, output_tokens=5),
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capacity.model_request",
            return_value=mock_response,
        )

        qv = QuestionValidity(model=mock_model)  # type: ignore[arg-type]
        result = await qv.wrap_run(mock_ctx, handler=mock_handler)

        mock_handler.assert_not_awaited()
        assert result.output == DEFAULT_INVALID_QUESTION_RESPONSE

    @pytest.mark.asyncio
    async def test_usage_is_incremented(
        self,
        mocker: MockerFixture,
        mock_model: _FakeModel,
        mock_ctx: RunContext,
        mock_handler: AsyncMock,
    ) -> None:
        """Test that token usage from the validity check is tracked."""
        request_usage = RequestUsage(input_tokens=50, output_tokens=5)
        mock_response = ModelResponse(
            parts=[TextPart(content=SUBJECT_ALLOWED)],
            usage=request_usage,
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capacity.model_request",
            return_value=mock_response,
        )

        qv = QuestionValidity(model=mock_model)  # type: ignore[arg-type]
        await qv.wrap_run(mock_ctx, handler=mock_handler)

        assert mock_ctx.usage.input_tokens == 50
        assert mock_ctx.usage.output_tokens == 5

    @pytest.mark.asyncio
    async def test_usage_is_incremented_on_rejection(
        self,
        mocker: MockerFixture,
        mock_model: _FakeModel,
        mock_ctx: RunContext,
        mock_handler: AsyncMock,
    ) -> None:
        """Test that token usage is tracked even when question is rejected."""
        request_usage = RequestUsage(input_tokens=30, output_tokens=2)
        mock_response = ModelResponse(
            parts=[TextPart(content=SUBJECT_REJECTED)],
            usage=request_usage,
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capacity.model_request",
            return_value=mock_response,
        )

        qv = QuestionValidity(model=mock_model)  # type: ignore[arg-type]
        await qv.wrap_run(mock_ctx, handler=mock_handler)

        assert mock_ctx.usage.input_tokens == 30
        assert mock_ctx.usage.output_tokens == 2

    @pytest.mark.asyncio
    async def test_rejection_result_contains_usage_in_state(
        self,
        mocker: MockerFixture,
        mock_model: _FakeModel,
        mock_ctx: RunContext,
        mock_handler: AsyncMock,
    ) -> None:
        """Test that the rejection AgentRunResult state carries the usage."""
        request_usage = RequestUsage(input_tokens=20, output_tokens=3)
        mock_response = ModelResponse(
            parts=[TextPart(content=SUBJECT_REJECTED)],
            usage=request_usage,
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capacity.model_request",
            return_value=mock_response,
        )

        qv = QuestionValidity(model=mock_model)  # type: ignore[arg-type]
        result = await qv.wrap_run(mock_ctx, handler=mock_handler)

        assert result._state.usage == mock_ctx.usage

    @pytest.mark.asyncio
    async def test_custom_invalid_response(
        self,
        mocker: MockerFixture,
        mock_model: _FakeModel,
        mock_ctx: RunContext,
        mock_handler: AsyncMock,
    ) -> None:
        """Test that a custom rejection message is used when set."""
        mock_response = ModelResponse(
            parts=[TextPart(content=SUBJECT_REJECTED)],
            usage=RequestUsage(),
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capacity.model_request",
            return_value=mock_response,
        )

        qv = QuestionValidity(
            model=mock_model,  # type: ignore[arg-type]
            invalid_question_response="Custom rejection.",
        )
        result = await qv.wrap_run(mock_ctx, handler=mock_handler)

        assert result.output == "Custom rejection."

    @pytest.mark.asyncio
    async def test_model_request_receives_correct_prompt(
        self,
        mocker: MockerFixture,
        mock_model: _FakeModel,
        mock_ctx: RunContext,
        mock_handler: AsyncMock,
    ) -> None:
        """Test that model_request is called with the built prompt."""
        mock_model_request = mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capacity.model_request",
            return_value=ModelResponse(
                parts=[TextPart(content=SUBJECT_ALLOWED)],
                usage=RequestUsage(),
            ),
        )

        qv = QuestionValidity(model=mock_model)  # type: ignore[arg-type]
        await qv.wrap_run(mock_ctx, handler=mock_handler)

        call_kwargs = mock_model_request.call_args
        assert call_kwargs.kwargs["model"] is qv.model
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) == 1
        assert "How do I create a pod?" in str(messages[0])

    @pytest.mark.asyncio
    async def test_wrap_run_with_none_prompt(
        self,
        mocker: MockerFixture,
        mock_model: _FakeModel,
        mock_handler: AsyncMock,
    ) -> None:
        """Test wrap_run when ctx.prompt is None."""
        ctx = mocker.Mock(spec=RunContext)
        ctx.prompt = None
        ctx.usage = RunUsage()

        mock_response = ModelResponse(
            parts=[TextPart(content=SUBJECT_REJECTED)],
            usage=RequestUsage(),
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capacity.model_request",
            return_value=mock_response,
        )

        qv = QuestionValidity(model=mock_model)  # type: ignore[arg-type]
        result = await qv.wrap_run(ctx, handler=mock_handler)

        assert result.output == DEFAULT_INVALID_QUESTION_RESPONSE

    @pytest.mark.asyncio
    async def test_wrap_run_with_sequence_prompt(
        self,
        mocker: MockerFixture,
        mock_model: _FakeModel,
        mock_handler: AsyncMock,
    ) -> None:
        """Test wrap_run when ctx.prompt is a Sequence[UserContent]."""
        ctx = mocker.Mock(spec=RunContext)
        ctx.prompt = ["How to", TextContent(content="scale a deployment?")]
        ctx.usage = RunUsage()

        mock_model_request = mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capacity.model_request",
            return_value=ModelResponse(
                parts=[TextPart(content=SUBJECT_ALLOWED)],
                usage=RequestUsage(),
            ),
        )

        qv = QuestionValidity(model=mock_model)  # type: ignore[arg-type]
        await qv.wrap_run(ctx, handler=mock_handler)

        messages = mock_model_request.call_args.kwargs["messages"]
        prompt_str = str(messages[0])
        assert "How to" in prompt_str
        assert "scale a deployment?" in prompt_str

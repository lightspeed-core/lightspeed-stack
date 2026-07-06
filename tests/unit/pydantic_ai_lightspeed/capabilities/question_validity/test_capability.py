"""Unit tests for pydantic_ai_lightspeed.capabilities.question_validity._capacity module."""

# pylint: disable=protected-access

import pytest
from pydantic import ValidationError
from pydantic_ai import AgentRunResult, RunContext
from pydantic_ai.messages import ImageUrl, ModelResponse, TextContent, TextPart
from pydantic_ai.usage import RequestUsage, RunUsage
from pytest_mock import MockerFixture, MockType

from constants import (
    DEFAULT_INVALID_QUESTION_RESPONSE,
    DEFAULT_MODEL_PROMPT,
)
from models.config import (
    QuestionValidityConfig,
)
from pydantic_ai_lightspeed.capabilities.question_validity._capability import (
    SUBJECT_ALLOWED,
    SUBJECT_REJECTED,
    QuestionValidity,
    _create_model_from_llama_stack_client,
    _extract_message_str_from_user_content,
)


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


class TestQuestionValidityConfigInit:
    """Tests for QuestionValidityConfig initialization."""

    def test_default_model_prompt(self) -> None:
        """Test that default model_prompt is used."""
        qv_config = QuestionValidityConfig(model_id="test")

        assert qv_config.model_prompt == DEFAULT_MODEL_PROMPT

    def test_default_invalid_question_response(self) -> None:
        """Test that default invalid_question_response is used."""
        qv_config = QuestionValidityConfig(model_id="test")

        assert qv_config.invalid_question_response == DEFAULT_INVALID_QUESTION_RESPONSE

    def test_custom_model_prompt(self) -> None:
        """Test that custom model_prompt can be provided."""
        qv_config = QuestionValidityConfig(
            model_id="test", model_prompt="custom prompt ${message}"
        )

        assert qv_config.model_prompt == "custom prompt ${message}"

    def test_custom_invalid_response(self) -> None:
        """Test that custom invalid_question_response can be provided."""
        qv_config = QuestionValidityConfig(
            model_id="test", invalid_question_response="Nope!"
        )

        assert qv_config.invalid_question_response == "Nope!"

    def test_missing_model_id_raises_validation_error(self) -> None:
        """Test that model_id is required."""
        with pytest.raises(ValidationError):
            QuestionValidityConfig()  # type: ignore[call-arg]

    def test_unknown_fields_rejected(self) -> None:
        """Test that extra fields are rejected."""
        with pytest.raises(ValidationError):
            QuestionValidityConfig(model_id="test", unknown_field="value")  # type: ignore[call-arg]


class TestCreateModelFromLlamaStackClient:
    """Tests for _create_model_from_llama_stack_client factory function."""

    _MODULE = "pydantic_ai_lightspeed.capabilities.question_validity._capability"

    def test_creates_model_with_correct_wiring(self, mocker: MockerFixture) -> None:
        """Test that the factory wires client, provider, and model correctly."""
        mock_client = mocker.Mock()
        mock_holder = mocker.patch(f"{self._MODULE}.AsyncLlamaStackClientHolder")
        mock_holder.return_value.get_client.return_value = mock_client

        mock_provider = mocker.Mock()
        mocker.patch(
            f"{self._MODULE}.llama_stack_provider_from_client",
            return_value=mock_provider,
        )

        mock_model_cls = mocker.patch(f"{self._MODULE}.LlamaStackResponsesModel")

        result = _create_model_from_llama_stack_client("test-model")

        mock_holder.return_value.get_client.assert_called_once()
        mock_model_cls.assert_called_once()
        call_args = mock_model_cls.call_args
        assert call_args.args[0] == "test-model"
        assert call_args.kwargs["provider"] is mock_provider
        settings = call_args.kwargs["settings"]
        assert settings == {"openai_store": False}
        assert result is mock_model_cls.return_value

    def test_passes_client_to_provider_factory(self, mocker: MockerFixture) -> None:
        """Test that the client from the holder is passed to the provider factory."""
        mock_client = mocker.Mock()
        mock_holder = mocker.patch(f"{self._MODULE}.AsyncLlamaStackClientHolder")
        mock_holder.return_value.get_client.return_value = mock_client

        mock_from_client = mocker.patch(
            f"{self._MODULE}.llama_stack_provider_from_client",
        )

        _create_model_from_llama_stack_client("any-model")

        mock_from_client.assert_called_once_with(mock_client)


class TestQuestionValidityInit:
    """Tests for QuestionValidity dataclass initialization."""

    _MODULE = "pydantic_ai_lightspeed.capabilities.question_validity._capability"

    def test_post_init_calls_create_model(self, mocker: MockerFixture) -> None:
        """Test that __post_init__ delegates to _create_model_from_llama_stack_client."""
        mock_create = mocker.patch(
            f"{self._MODULE}._create_model_from_llama_stack_client",
        )
        config = QuestionValidityConfig(model_id="my-model")

        QuestionValidity(config=config)

        mock_create.assert_called_once_with("my-model")

    def test_model_is_assigned_from_factory(self, mocker: MockerFixture) -> None:
        """Test that the model returned by the factory is stored on the instance."""
        mock_model = mocker.Mock()
        mocker.patch(
            f"{self._MODULE}._create_model_from_llama_stack_client",
            return_value=mock_model,
        )
        config = QuestionValidityConfig(model_id="test")

        qv = QuestionValidity(config=config)

        assert qv._model is mock_model


class TestBuildPrompt:
    """Tests for QuestionValidity._build_prompt method."""

    _MODULE = "pydantic_ai_lightspeed.capabilities.question_validity._capability"

    @pytest.fixture(autouse=True)
    def _mock_create_model(self, mocker: MockerFixture) -> None:
        """Mock _create_model_from_llama_stack_client for all tests."""
        mocker.patch(f"{self._MODULE}._create_model_from_llama_stack_client")

    @pytest.fixture(name="question_validity")
    def question_validity_fixture(self) -> QuestionValidity:
        """Create a QuestionValidity instance with a mock model."""
        config = QuestionValidityConfig(model_id="test")
        return QuestionValidity(config=config)

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
        config = QuestionValidityConfig(
            model_id="test",
            model_prompt="Is '${message}' valid? ${allowed}/${rejected}",
        )
        qv = QuestionValidity(config=config)

        prompt = qv._build_prompt("my question")

        assert prompt == f"Is 'my question' valid? {SUBJECT_ALLOWED}/{SUBJECT_REJECTED}"


class TestWrapRun:
    """Tests for QuestionValidity.wrap_run method."""

    _MODULE = "pydantic_ai_lightspeed.capabilities.question_validity._capability"

    @pytest.fixture(autouse=True)
    def _mock_create_model(self, mocker: MockerFixture) -> None:
        """Mock _create_model_from_llama_stack_client for all tests."""
        mocker.patch(f"{self._MODULE}._create_model_from_llama_stack_client")

    @pytest.fixture(name="mock_ctx")
    def mock_ctx_fixture(self, mocker: MockerFixture) -> RunContext:
        """Create a mock RunContext."""
        ctx = mocker.Mock(spec=RunContext)
        ctx.prompt = "How do I create a pod?"
        ctx.usage = RunUsage()
        return ctx

    @pytest.fixture(name="mock_handler")
    def mock_handler_fixture(self, mocker: MockerFixture) -> MockType:
        """Create a mock WrapRunHandler."""
        handler = mocker.AsyncMock()
        handler.return_value = mocker.Mock(spec=AgentRunResult)
        return handler

    @pytest.mark.asyncio
    async def test_allowed_question_calls_handler(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that an allowed question proceeds to the handler."""
        mock_response = ModelResponse(
            parts=[TextPart(content=SUBJECT_ALLOWED)],
            usage=RequestUsage(input_tokens=10, output_tokens=1),
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capability.model_request",
            return_value=mock_response,
        )

        config = QuestionValidityConfig(model_id="test")
        qv = QuestionValidity(config=config)
        result = await qv.wrap_run(mock_ctx, handler=mock_handler)

        mock_handler.assert_awaited_once()
        assert result == mock_handler.return_value

    @pytest.mark.asyncio
    async def test_rejected_question_returns_rejection(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that a rejected question short-circuits with rejection message."""
        mock_response = ModelResponse(
            parts=[TextPart(content=SUBJECT_REJECTED)],
            usage=RequestUsage(input_tokens=10, output_tokens=1),
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capability.model_request",
            return_value=mock_response,
        )

        config = QuestionValidityConfig(model_id="test")
        qv = QuestionValidity(config=config)
        result = await qv.wrap_run(mock_ctx, handler=mock_handler)

        mock_handler.assert_not_awaited()
        assert isinstance(result, AgentRunResult)
        assert result.output == DEFAULT_INVALID_QUESTION_RESPONSE

    @pytest.mark.asyncio
    async def test_unexpected_response_treated_as_rejected(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that an unexpected model response is treated as rejection."""
        mock_response = ModelResponse(
            parts=[TextPart(content="I don't understand")],
            usage=RequestUsage(input_tokens=10, output_tokens=5),
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capability.model_request",
            return_value=mock_response,
        )

        config = QuestionValidityConfig(model_id="test")
        qv = QuestionValidity(config=config)
        result = await qv.wrap_run(mock_ctx, handler=mock_handler)

        mock_handler.assert_not_awaited()
        assert result.output == DEFAULT_INVALID_QUESTION_RESPONSE

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "response_text",
        [" ALLOWED", "ALLOWED ", " ALLOWED ", "ALLOWED\n"],
        ids=["leading-space", "trailing-space", "both-spaces", "trailing-newline"],
    )
    async def test_allowed_with_whitespace_still_accepted(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
        response_text: str,
    ) -> None:
        """Test that ALLOWED with surrounding whitespace is still accepted."""
        mock_response = ModelResponse(
            parts=[TextPart(content=response_text)],
            usage=RequestUsage(input_tokens=10, output_tokens=1),
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capability.model_request",
            return_value=mock_response,
        )

        config = QuestionValidityConfig(model_id="test")
        qv = QuestionValidity(config=config)
        result = await qv.wrap_run(mock_ctx, handler=mock_handler)

        mock_handler.assert_awaited_once()
        assert result == mock_handler.return_value

    @pytest.mark.asyncio
    async def test_usage_is_incremented(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that token usage from the validity check is tracked."""
        request_usage = RequestUsage(input_tokens=50, output_tokens=5)
        mock_response = ModelResponse(
            parts=[TextPart(content=SUBJECT_ALLOWED)],
            usage=request_usage,
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capability.model_request",
            return_value=mock_response,
        )

        config = QuestionValidityConfig(model_id="test")
        qv = QuestionValidity(config=config)
        await qv.wrap_run(mock_ctx, handler=mock_handler)

        assert mock_ctx.usage.input_tokens == 50
        assert mock_ctx.usage.output_tokens == 5

    @pytest.mark.asyncio
    async def test_usage_is_incremented_on_rejection(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that token usage is tracked even when question is rejected."""
        request_usage = RequestUsage(input_tokens=30, output_tokens=2)
        mock_response = ModelResponse(
            parts=[TextPart(content=SUBJECT_REJECTED)],
            usage=request_usage,
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capability.model_request",
            return_value=mock_response,
        )

        config = QuestionValidityConfig(model_id="test")
        qv = QuestionValidity(config=config)
        await qv.wrap_run(mock_ctx, handler=mock_handler)

        assert mock_ctx.usage.input_tokens == 30
        assert mock_ctx.usage.output_tokens == 2

    @pytest.mark.asyncio
    async def test_rejection_result_contains_usage_in_state(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that the rejection AgentRunResult state carries the usage."""
        request_usage = RequestUsage(input_tokens=20, output_tokens=3)
        mock_response = ModelResponse(
            parts=[TextPart(content=SUBJECT_REJECTED)],
            usage=request_usage,
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capability.model_request",
            return_value=mock_response,
        )

        config = QuestionValidityConfig(model_id="test")
        qv = QuestionValidity(config=config)
        result = await qv.wrap_run(mock_ctx, handler=mock_handler)

        assert result._state.usage == mock_ctx.usage

    @pytest.mark.asyncio
    async def test_custom_invalid_response(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that a custom rejection message is used when set."""
        mock_response = ModelResponse(
            parts=[TextPart(content=SUBJECT_REJECTED)],
            usage=RequestUsage(),
        )
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capability.model_request",
            return_value=mock_response,
        )

        config = QuestionValidityConfig(
            model_id="test", invalid_question_response="Custom rejection."
        )
        qv = QuestionValidity(config=config)
        result = await qv.wrap_run(mock_ctx, handler=mock_handler)

        assert result.output == "Custom rejection."

    @pytest.mark.asyncio
    async def test_model_request_receives_correct_prompt(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that model_request is called with the built prompt."""
        mock_model_request = mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capability.model_request",
            return_value=ModelResponse(
                parts=[TextPart(content=SUBJECT_ALLOWED)],
                usage=RequestUsage(),
            ),
        )

        config = QuestionValidityConfig(model_id="test")
        qv = QuestionValidity(config=config)
        await qv.wrap_run(mock_ctx, handler=mock_handler)

        call_kwargs = mock_model_request.call_args
        assert call_kwargs.kwargs["model"] is qv._model
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) == 1
        assert "How do I create a pod?" in str(messages[0])

    @pytest.mark.asyncio
    async def test_wrap_run_with_none_prompt(
        self,
        mocker: MockerFixture,
        mock_handler: MockType,
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
            "pydantic_ai_lightspeed.capabilities.question_validity._capability.model_request",
            return_value=mock_response,
        )

        config = QuestionValidityConfig(model_id="test")
        qv = QuestionValidity(config=config)
        result = await qv.wrap_run(ctx, handler=mock_handler)

        assert result.output == DEFAULT_INVALID_QUESTION_RESPONSE

    @pytest.mark.asyncio
    async def test_wrap_run_propagates_model_request_error(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that model_request exceptions propagate to the caller."""
        mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capability.model_request",
            side_effect=RuntimeError("connection failed"),
        )

        config = QuestionValidityConfig(model_id="test")
        qv = QuestionValidity(config=config)

        with pytest.raises(RuntimeError, match="connection failed"):
            await qv.wrap_run(mock_ctx, handler=mock_handler)

        mock_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_wrap_run_with_sequence_prompt(
        self,
        mocker: MockerFixture,
        mock_handler: MockType,
    ) -> None:
        """Test wrap_run when ctx.prompt is a Sequence[UserContent]."""
        ctx = mocker.Mock(spec=RunContext)
        ctx.prompt = ["How to", TextContent(content="scale a deployment?")]
        ctx.usage = RunUsage()

        mock_model_request = mocker.patch(
            "pydantic_ai_lightspeed.capabilities.question_validity._capability.model_request",
            return_value=ModelResponse(
                parts=[TextPart(content=SUBJECT_ALLOWED)],
                usage=RequestUsage(),
            ),
        )

        config = QuestionValidityConfig(model_id="test")
        qv = QuestionValidity(config=config)
        await qv.wrap_run(ctx, handler=mock_handler)

        messages = mock_model_request.call_args.kwargs["messages"]
        prompt_str = str(messages[0])
        assert "How to" in prompt_str
        assert "scale a deployment?" in prompt_str

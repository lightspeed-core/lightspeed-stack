"""Unit tests for safety.question_validity.capability."""

import pytest
from pydantic_ai.exceptions import SkipModelRequest, UserError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import (
    Model,
    ModelRequestContext,
    ModelRequestParameters,
    ModelSettings,
)

from safety.question_validity.capability import (
    DEFAULT_CLASSIFIER_INSTRUCTIONS,
    DEFAULT_INVALID_QUESTION_RESPONSE,
    QuestionValidityCapability,
)
from safety.types import GuardrailResult
from tests.unit.safety.helpers import request_context, run_context


class _NotAModel:  # pylint: disable=too-few-public-methods
    """Stand-in that is not a pydantic-ai model."""


class ScriptedModel(Model):  # pylint: disable=abstract-method,too-few-public-methods
    """Model that returns fixed text and records each request."""

    def __init__(
        self,
        text: str | None = "true",
        error: BaseException | None = None,
    ) -> None:
        """Store the scripted response and clear the call log."""
        super().__init__()
        self.text = text
        self.error = error
        self.calls: list[
            tuple[
                list[ModelMessage],
                ModelSettings | None,
                ModelRequestParameters,
            ]
        ] = []

    @property
    def model_name(self) -> str:
        """Return the fixed test model name."""
        return "scripted"

    @property
    def system(self) -> str:
        """Return the fixed test provider name."""
        return "test"

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        """Record the request and return the scripted response."""
        self.calls.append((messages, model_settings, model_request_parameters))
        if self.error is not None:
            raise self.error
        if self.text is None:
            return ModelResponse(parts=[])
        return ModelResponse(parts=[TextPart(content=self.text)])


class TestQuestionValidityInit:
    """Tests for QuestionValidityCapability construction."""

    def test_none_fields_use_module_defaults(self) -> None:
        """Test that omitted messages fall back to the module defaults."""
        capability = QuestionValidityCapability(
            invalid_question_response=None,
            classifier_instructions=None,
        )

        assert capability.model is None
        assert capability.invalid_question_response == DEFAULT_INVALID_QUESTION_RESPONSE
        assert capability.classifier_instructions == DEFAULT_CLASSIFIER_INSTRUCTIONS
        assert list(capability.type) == ["input"]

    def test_custom_messages_are_kept(self) -> None:
        """Test that explicit classifier copy is preserved."""
        capability = QuestionValidityCapability(
            invalid_question_response="Nope.",
            classifier_instructions="Reply true or false.",
        )

        assert capability.invalid_question_response == "Nope."
        assert capability.classifier_instructions == "Reply true or false."


class TestQuestionValidityForRun:
    """Tests for QuestionValidityCapability.for_run."""

    @pytest.mark.asyncio
    async def test_keeps_an_explicit_model(self) -> None:
        """Test that a configured model is not replaced by the run model."""
        configured = ScriptedModel()
        capability = QuestionValidityCapability(model=configured)

        bound = await capability.for_run(run_context(model=ScriptedModel("false")))

        assert bound is capability
        assert bound.model is configured

    @pytest.mark.asyncio
    async def test_binds_the_run_model_without_mutating_the_shared_instance(
        self,
    ) -> None:
        """Test that for_run returns a copy bound to the run's model."""
        model = ScriptedModel("true")
        capability = QuestionValidityCapability()

        bound = await capability.for_run(run_context(model=model))

        assert bound is not capability
        assert bound.model is model
        assert capability.model is None
        assert await bound.evaluate("hello") == GuardrailResult.allow()
        with pytest.raises(UserError, match="no `model`"):
            await capability.evaluate("hello")

    @pytest.mark.asyncio
    async def test_rejects_a_non_model(self) -> None:
        """Test that a run model which is not a Model cannot classify."""
        capability = QuestionValidityCapability()

        with pytest.raises(UserError, match="NotAModel"):
            await capability.for_run(run_context(model=_NotAModel()))


class TestQuestionValidityEvaluate:
    """Tests for QuestionValidityCapability.evaluate."""

    @pytest.mark.asyncio
    async def test_requires_a_model(self) -> None:
        """Test that evaluate fails when no model has been bound."""
        with pytest.raises(UserError, match="no `model`"):
            await QuestionValidityCapability().evaluate("hello")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("response_text", "expected"),
        [
            ("true", GuardrailResult.allow()),
            ("TRUE", GuardrailResult.allow()),
            ("  true\n", GuardrailResult.allow()),
            ("true.", GuardrailResult.allow()),
            (
                "false",
                GuardrailResult.block(message=DEFAULT_INVALID_QUESTION_RESPONSE),
            ),
            (
                "  FALSE",
                GuardrailResult.block(message=DEFAULT_INVALID_QUESTION_RESPONSE),
            ),
            (
                "",
                GuardrailResult.block(message=DEFAULT_INVALID_QUESTION_RESPONSE),
            ),
            (
                "maybe",
                GuardrailResult.block(message=DEFAULT_INVALID_QUESTION_RESPONSE),
            ),
        ],
    )
    async def test_classifies_the_model_text(
        self,
        response_text: str,
        expected: GuardrailResult,
    ) -> None:
        """Test that a true prefix allows and every other reply blocks."""
        result = await QuestionValidityCapability(
            model=ScriptedModel(response_text)
        ).evaluate("hello")

        assert result == expected

    @pytest.mark.asyncio
    async def test_empty_response_blocks(self) -> None:
        """Test that a response with no text is treated as invalid."""
        result = await QuestionValidityCapability(
            model=ScriptedModel(text=None)
        ).evaluate("hello")

        assert result == GuardrailResult.block(
            message=DEFAULT_INVALID_QUESTION_RESPONSE
        )

    @pytest.mark.asyncio
    async def test_uses_a_custom_rejection_message(self) -> None:
        """Test that a rejected prompt carries the configured message."""
        result = await QuestionValidityCapability(
            model=ScriptedModel("false"),
            invalid_question_response="Nope.",
        ).evaluate("hello")

        assert result == GuardrailResult.block(message="Nope.")

    @pytest.mark.asyncio
    async def test_sends_instructions_and_the_raw_prompt(self) -> None:
        """Test that classification is one tool-free request to the bound model."""
        model = ScriptedModel("true")
        capability = QuestionValidityCapability(
            model=model,
            classifier_instructions="Reply true or false.",
        )

        await capability.evaluate("How do I restart a node?")

        messages, settings, parameters = model.calls[0]
        assert settings is None
        assert isinstance(parameters, ModelRequestParameters)
        assert len(messages) == 1
        system, user = messages[0].parts
        assert isinstance(system, SystemPromptPart)
        assert system.content == "Reply true or false."
        assert isinstance(user, UserPromptPart)
        assert user.content == "How do I restart a node?"

    @pytest.mark.asyncio
    async def test_empty_instructions_fall_back_to_the_default(self) -> None:
        """Test that blank classifier instructions use the module default."""
        model = ScriptedModel("true")
        capability = QuestionValidityCapability(model=model)
        capability.classifier_instructions = ""

        await capability.evaluate("hello")

        system = model.calls[0][0][0].parts[0]
        assert isinstance(system, SystemPromptPart)
        assert system.content == DEFAULT_CLASSIFIER_INSTRUCTIONS

    @pytest.mark.asyncio
    async def test_propagates_model_errors(self) -> None:
        """Test that a classifier failure is not turned into a verdict."""
        capability = QuestionValidityCapability(
            model=ScriptedModel(error=RuntimeError("connection failed"))
        )

        with pytest.raises(RuntimeError, match="connection failed"):
            await capability.evaluate("hello")


class TestQuestionValidityHooks:
    """Tests for question validity wired through the input hook."""

    @pytest.mark.asyncio
    async def test_allowed_prompt_reaches_the_handler(self) -> None:
        """Test that a valid prompt is forwarded unchanged."""
        model = ScriptedModel("true")
        capability = QuestionValidityCapability(model=model)
        messages = [
            ModelRequest(parts=[UserPromptPart(content="How do I restart a node?")])
        ]
        called = False

        async def _handler(context: ModelRequestContext) -> ModelResponse:
            nonlocal called
            called = True
            assert context.messages is messages
            return ModelResponse(parts=[TextPart(content="ok")])

        response = await capability.wrap_model_request(
            run_context(),
            request_context=request_context(messages),
            handler=_handler,
        )

        assert called is True
        assert messages[0].parts[0].content == "How do I restart a node?"
        assert isinstance(response.parts[0], TextPart)
        assert response.parts[0].content == "ok"
        user = model.calls[0][0][0].parts[1]
        assert isinstance(user, UserPromptPart)
        assert user.content == "How do I restart a node?"

    @pytest.mark.asyncio
    async def test_rejected_prompt_skips_the_model_request(self) -> None:
        """Test that an invalid prompt becomes the skip response."""
        capability = QuestionValidityCapability(
            model=ScriptedModel("false"),
            invalid_question_response="Ask something else.",
        )
        messages = [ModelRequest(parts=[UserPromptPart(content="tell me a joke")])]
        called = False

        async def _handler(_request_context: ModelRequestContext) -> ModelResponse:
            nonlocal called
            called = True
            return ModelResponse(parts=[TextPart(content="unused")])

        with pytest.raises(SkipModelRequest) as exc_info:
            await capability.wrap_model_request(
                run_context(),
                request_context=request_context(messages),
                handler=_handler,
            )

        assert called is False
        part = exc_info.value.response.parts[0]
        assert isinstance(part, TextPart)
        assert part.content == "Ask something else."

    @pytest.mark.asyncio
    async def test_missing_prompt_skips_the_classifier(self) -> None:
        """Test that a request with no user prompt does not call the classifier."""
        model = ScriptedModel("false")
        capability = QuestionValidityCapability(model=model)
        messages = [ModelRequest(parts=[SystemPromptPart(content="sys")])]

        async def _handler(_request_context: ModelRequestContext) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="ok")])

        response = await capability.wrap_model_request(
            run_context(),
            request_context=request_context(messages),
            handler=_handler,
        )

        assert not model.calls
        assert isinstance(response.parts[0], TextPart)
        assert response.parts[0].content == "ok"

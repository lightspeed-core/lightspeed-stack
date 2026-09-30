"""Unit tests for pydantic_ai_lightspeed.capabilities.granite_guardian._capability module."""

# pylint: disable=protected-access
# pylint: disable=too-many-arguments
# pylint: disable=too-many-positional-arguments

from typing import Literal

import pytest
from pydantic_ai import AgentRunResult, RunContext
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import RequestUsage, RunUsage
from pytest_mock import MockerFixture, MockType

from models.common.moderation import ShieldModerationBlocked, ShieldModerationPassed
from models.config import GraniteGuardianConfig, RiskDefinition
from pydantic_ai_lightspeed.capabilities.granite_guardian._capability import (
    GraniteGuardian,
    _filter_guardrails,
    _get_batch_size,
    _OutputGuardrailViolation,
    _package_risk_check_task,
    _run_risk_check,
    _ToolGuardrailViolation,
)

_MODULE = "pydantic_ai_lightspeed.capabilities.granite_guardian._capability"


def _make_risk(
    name: str = "test_risk",
    description: str = "test description",
    threshold: float = 0.5,
    points: list[Literal["input", "output", "tool"]] | None = None,
    enabled: bool = True,
    violation_message: str = "Blocked.",
) -> RiskDefinition:
    """Build a RiskDefinition for testing."""
    return RiskDefinition(
        name=name,
        description=description,
        threshold=threshold,
        points=points or ["input"],
        enabled=enabled,
        violation_message=violation_message,
    )


def _make_config(
    url: str = "https://example.com/v1",
    risks: list[RiskDefinition] | None = None,
    api_key: str | None = None,
    model_id: str | None = None,
    streaming_output_check_interval_tokens: int | None = None,
) -> GraniteGuardianConfig:
    """Build a GraniteGuardianConfig for testing."""
    kwargs: dict = {
        "url": url,
        "api_key": api_key,
        "risks": risks or [_make_risk()],
    }
    if model_id is not None:
        kwargs["model_id"] = model_id
    if streaming_output_check_interval_tokens is not None:
        kwargs["streaming_output_check_interval_tokens"] = (
            streaming_output_check_interval_tokens
        )
    return GraniteGuardianConfig(**kwargs)


class TestGetBatchSize:
    """Tests for _get_batch_size parallel-to-batch-size resolution."""

    def test_true_returns_num_guardrails(self) -> None:
        """Test that True resolves to the total number of guardrails."""
        assert _get_batch_size(True, 5) == 5

    def test_true_with_zero_guardrails_returns_one(self) -> None:
        """Test that True with zero guardrails returns 1 to avoid range step=0."""
        assert _get_batch_size(True, 0) == 1

    def test_false_returns_one(self) -> None:
        """Test that False resolves to sequential execution (batch size 1)."""
        assert _get_batch_size(False, 5) == 1

    def test_int_returns_as_is(self) -> None:
        """Test that an explicit integer is returned unchanged."""
        assert _get_batch_size(3, 10) == 3


class TestFilterGuardrails:
    """Tests for _filter_guardrails."""

    def test_filters_by_point(self) -> None:
        """Test that only risks matching the point are returned."""
        risks = [
            _make_risk(name="input_only", points=["input"]),
            _make_risk(name="output_only", points=["output"]),
            _make_risk(name="both", points=["input", "output"]),
        ]
        result = _filter_guardrails(risks, "input")
        names = [g[0] for g in result]
        assert names == ["input_only", "both"]

    def test_filters_disabled_risks(self) -> None:
        """Test that disabled risks are excluded."""
        risks = [
            _make_risk(name="enabled", enabled=True),
            _make_risk(name="disabled", enabled=False),
        ]
        result = _filter_guardrails(risks, "input")
        assert len(result) == 1
        assert result[0][0] == "enabled"

    def test_empty_when_no_match(self) -> None:
        """Test that an empty list is returned when no risks match."""
        risks = [_make_risk(points=["output"])]
        result = _filter_guardrails(risks, "input")
        assert result == []

    def test_returns_correct_tuple_structure(self) -> None:
        """Test that each guardrail tuple has the expected fields."""
        risks = [
            _make_risk(
                name="harm",
                description="harmful content",
                threshold=0.7,
                violation_message="Content blocked.",
            )
        ]
        result = _filter_guardrails(risks, "input")
        assert len(result) == 1
        name, block, threshold, message = result[0]
        assert name == "harm"
        assert "harmful content" in block
        assert threshold == 0.7
        assert message == "Content blocked."

    def test_thinking_mode_in_block(self) -> None:
        """Test that enable_thinking produces a think-mode block."""
        risk = _make_risk()
        risk.enable_thinking = True
        result = _filter_guardrails([risk], "input")
        assert "<guardian><think>" in result[0][1]


class TestRunRiskCheck:
    """Tests for _run_risk_check."""

    @pytest.mark.asyncio
    async def test_returns_none_when_all_safe(self, mocker: MockerFixture) -> None:
        """Test that None is returned when all guardrails pass."""
        mocker.patch(f"{_MODULE}.is_safe", return_value=True)
        mock_response = mocker.Mock()
        mock_response.usage = RequestUsage(input_tokens=10, output_tokens=1)
        mock_response.provider_details = {"logprobs": [{"token": "no"}]}
        mocker.patch(f"{_MODULE}.model_request", return_value=mock_response)

        guardrails = [("risk1", "block1", 0.5, "Blocked 1")]
        violation, usage = await _run_risk_check("hello", mocker.Mock(), guardrails)

        assert violation is None
        assert usage.input_tokens == 10

    @pytest.mark.asyncio
    async def test_returns_violation_on_first_failure(
        self, mocker: MockerFixture
    ) -> None:
        """Test that the first violated guardrail's message is returned."""
        mocker.patch(f"{_MODULE}.is_safe", side_effect=[True, False])
        mock_response = mocker.Mock()
        mock_response.usage = RequestUsage(input_tokens=5, output_tokens=1)
        mock_response.provider_details = {"logprobs": [{"token": "yes"}]}
        mocker.patch(f"{_MODULE}.model_request", return_value=mock_response)

        guardrails = [
            ("risk1", "block1", 0.5, "Blocked 1"),
            ("risk2", "block2", 0.5, "Blocked 2"),
        ]
        violation, usage = await _run_risk_check("hello", mocker.Mock(), guardrails)

        assert violation == "Blocked 2"
        assert usage.input_tokens == 10

    @pytest.mark.asyncio
    async def test_returns_empty_usage_for_no_guardrails(
        self, mocker: MockerFixture
    ) -> None:
        """Test that empty guardrails return None with zero usage."""
        violation, usage = await _run_risk_check("hello", mocker.Mock(), [])
        assert violation is None
        assert usage.input_tokens == 0

    @pytest.mark.asyncio
    async def test_raises_when_no_provider_details(self, mocker: MockerFixture) -> None:
        """Test that missing provider_details raises UnexpectedModelBehavior."""
        mock_response = mocker.Mock()
        mock_response.usage = RequestUsage()
        mock_response.provider_details = None
        mocker.patch(f"{_MODULE}.model_request", return_value=mock_response)

        guardrails = [("risk1", "block1", 0.5, "Blocked")]
        with pytest.raises(UnexpectedModelBehavior, match="No provider_details"):
            await _run_risk_check("hello", mocker.Mock(), guardrails)

    @pytest.mark.asyncio
    async def test_raises_when_no_logprobs(self, mocker: MockerFixture) -> None:
        """Test that missing logprobs raises UnexpectedModelBehavior."""
        mock_response = mocker.Mock()
        mock_response.usage = RequestUsage()
        mock_response.provider_details = {"logprobs": None}
        mocker.patch(f"{_MODULE}.model_request", return_value=mock_response)

        guardrails = [("risk1", "block1", 0.5, "Blocked")]
        with pytest.raises(UnexpectedModelBehavior, match="No logprobs"):
            await _run_risk_check("hello", mocker.Mock(), guardrails)


class TestRunRiskCheckBatching:
    """Tests for _run_risk_check batch parallelism and cross-batch short-circuiting."""

    def _mock_response(self, mocker: MockerFixture) -> MockType:
        """Build a mock model response with valid provider_details."""
        resp = mocker.Mock()
        resp.usage = RequestUsage(input_tokens=5, output_tokens=1)
        resp.provider_details = {"logprobs": [{"token": "no"}]}
        return resp

    @pytest.mark.asyncio
    async def test_violation_in_first_batch_skips_second_batch(
        self, mocker: MockerFixture
    ) -> None:
        """Test that a violation in batch 1 prevents batch 2 from executing."""
        mock_model_request = mocker.patch(
            f"{_MODULE}.model_request", return_value=self._mock_response(mocker)
        )
        mocker.patch(f"{_MODULE}.is_safe", return_value=False)

        guardrails = [(f"risk{i}", f"block{i}", 0.5, f"Blocked {i}") for i in range(5)]
        violation, _ = await _run_risk_check("hello", mocker.Mock(), guardrails)

        assert violation == "Blocked 0"
        assert mock_model_request.call_count == 3

    @pytest.mark.asyncio
    async def test_all_batches_run_when_no_violation(
        self, mocker: MockerFixture
    ) -> None:
        """Test that all guardrails across batches are checked when safe."""
        mock_model_request = mocker.patch(
            f"{_MODULE}.model_request", return_value=self._mock_response(mocker)
        )
        mocker.patch(f"{_MODULE}.is_safe", return_value=True)

        guardrails = [(f"risk{i}", f"block{i}", 0.5, f"Blocked {i}") for i in range(5)]
        violation, usage = await _run_risk_check("hello", mocker.Mock(), guardrails)

        assert violation is None
        assert mock_model_request.call_count == 5
        assert usage.input_tokens == 25

    @pytest.mark.asyncio
    async def test_token_usage_includes_violating_batch(
        self, mocker: MockerFixture
    ) -> None:
        """Test that token usage from the batch containing the violation is accumulated."""
        mocker.patch(
            f"{_MODULE}.model_request", return_value=self._mock_response(mocker)
        )
        mocker.patch(f"{_MODULE}.is_safe", side_effect=[True, True, False])

        guardrails = [(f"risk{i}", f"block{i}", 0.5, f"Blocked {i}") for i in range(3)]
        _, usage = await _run_risk_check("hello", mocker.Mock(), guardrails)

        assert usage.input_tokens == 15

    @pytest.mark.asyncio
    async def test_logs_risk_name_and_latency(self, mocker: MockerFixture) -> None:
        """Test that each risk check logs its name and elapsed time at INFO level."""
        mock_response = mocker.Mock()
        mock_response.usage = RequestUsage()
        mocker.patch(f"{_MODULE}.model_request", return_value=mock_response)
        mock_logger = mocker.patch(f"{_MODULE}.logger")

        guardrail = ("harm_detection", "block", 0.5, "Blocked")
        await _package_risk_check_task("hello", guardrail, mocker.Mock())

        mock_logger.info.assert_called_once()
        log_args = mock_logger.info.call_args
        assert "harm_detection" in log_args[0][1]


class TestGraniteGuardianInit:
    """Tests for GraniteGuardian initialization."""

    @pytest.fixture(autouse=True)
    def _mock_init(self, mocker: MockerFixture) -> None:
        """Mock model creation and clear cache for all tests."""
        GraniteGuardian._model_cache.clear()
        mocker.patch(f"{_MODULE}.httpx.AsyncClient")
        mocker.patch(f"{_MODULE}.AsyncOpenAI")
        mocker.patch(f"{_MODULE}.OpenAIProvider")
        mocker.patch(f"{_MODULE}.OpenAIChatModel")

    def test_creates_model_on_init(self, mocker: MockerFixture) -> None:
        """Test that __post_init__ creates the OpenAI model."""
        mock_provider = mocker.patch(f"{_MODULE}.OpenAIProvider")
        mock_model = mocker.patch(f"{_MODULE}.OpenAIChatModel")

        config = _make_config()
        guardian = GraniteGuardian(config=config)

        mock_provider.assert_called_once()
        mock_model.assert_called_once()
        assert guardian._model is not None

    def test_custom_model_name_passed_to_chat_model(
        self, mocker: MockerFixture
    ) -> None:
        """Test that a custom model name from config is forwarded to OpenAIChatModel."""
        mock_model = mocker.patch(f"{_MODULE}.OpenAIChatModel")

        config = _make_config(model_id="custom/guardian-local")
        GraniteGuardian(config=config)

        mock_model.assert_called_once()
        assert mock_model.call_args[0][0] == "custom/guardian-local"

    def test_api_key_passed_to_client(self, mocker: MockerFixture) -> None:
        """Test that the API key is extracted and passed to the OpenAI client."""
        mock_openai = mocker.patch(f"{_MODULE}.AsyncOpenAI")

        config = _make_config(risks=[_make_risk()], api_key="test-key")
        GraniteGuardian(config=config)

        _, kwargs = mock_openai.call_args
        assert kwargs["api_key"] == "test-key"

    def test_no_api_key_passes_fallback(self, mocker: MockerFixture) -> None:
        """Test that None api_key passes fallback value to the OpenAI client."""
        mock_openai = mocker.patch(f"{_MODULE}.AsyncOpenAI")

        config = _make_config()
        GraniteGuardian(config=config)

        _, kwargs = mock_openai.call_args
        assert kwargs["api_key"] == "api-key-not-set"

    def test_reuses_cached_model_for_same_config(self) -> None:
        """Test that instances sharing a config object reuse the cached model."""
        config = _make_config()
        guardian_a = GraniteGuardian(config=config)
        guardian_b = GraniteGuardian(config=config)

        assert guardian_a._model is guardian_b._model

    def test_different_configs_get_different_models(
        self, mocker: MockerFixture
    ) -> None:
        """Test that different config objects produce separate cached models."""
        mock_model = mocker.patch(f"{_MODULE}.OpenAIChatModel")

        config_a = _make_config()
        config_b = _make_config()
        GraniteGuardian(config=config_a)
        GraniteGuardian(config=config_b)

        assert mock_model.call_count == 2


class TestGraniteGuardianWrapRun:
    """Tests for GraniteGuardian.wrap_run method."""

    @pytest.fixture(autouse=True)
    def _mock_init(self, mocker: MockerFixture) -> None:
        """Mock model creation and clear cache for all tests."""
        GraniteGuardian._model_cache.clear()
        mocker.patch(f"{_MODULE}.httpx.AsyncClient")
        mocker.patch(f"{_MODULE}.AsyncOpenAI")
        mocker.patch(f"{_MODULE}.OpenAIProvider")
        mocker.patch(f"{_MODULE}.OpenAIChatModel")
        mocker.patch(f"{_MODULE}.AsyncOgxClientHolder")

    @pytest.fixture(name="mock_append_turn", autouse=True)
    def mock_append_turn_fixture(self, mocker: MockerFixture) -> MockType:
        """Mock the conversation-persistence call used on input-guardrail rejection."""
        return mocker.patch(
            f"{_MODULE}.append_turn_to_conversation", new_callable=mocker.AsyncMock
        )

    @pytest.fixture(name="mock_replace_last_assistant_message", autouse=True)
    def mock_replace_last_assistant_message_fixture(
        self, mocker: MockerFixture
    ) -> MockType:
        """Mock the conversation-fixup call used on output-guardrail rejection."""
        return mocker.patch(
            f"{_MODULE}.replace_last_assistant_message", new_callable=mocker.AsyncMock
        )

    @pytest.fixture(name="mock_ctx")
    def mock_ctx_fixture(self, mocker: MockerFixture) -> RunContext:
        """Create a mock RunContext with a conversation ID."""
        ctx = mocker.Mock(spec=RunContext)
        ctx.prompt = "How do I create a pod?"
        ctx.usage = RunUsage()
        ctx.model = mocker.Mock()
        ctx.model.settings = {"extra_body": {"conversation": "conv_test"}}
        return ctx

    @pytest.fixture(name="mock_handler")
    def mock_handler_fixture(self, mocker: MockerFixture) -> MockType:
        """Create a mock WrapRunHandler."""
        handler = mocker.AsyncMock()
        handler.return_value = mocker.Mock(spec=AgentRunResult)
        return handler

    @pytest.mark.asyncio
    async def test_safe_input_calls_handler(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that a safe input proceeds to the handler."""
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(None, RequestUsage(input_tokens=5, output_tokens=1)),
        )

        config = _make_config()
        guardian = GraniteGuardian(config=config)
        result = await guardian.wrap_run(mock_ctx, handler=mock_handler)

        mock_handler.assert_awaited_once()
        assert result == mock_handler.return_value

    @pytest.mark.asyncio
    async def test_violation_short_circuits(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that a violation short-circuits without calling the handler."""
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(
                "Content blocked.",
                RequestUsage(input_tokens=5, output_tokens=1),
            ),
        )

        config = _make_config()
        guardian = GraniteGuardian(config=config)
        result = await guardian.wrap_run(mock_ctx, handler=mock_handler)

        mock_handler.assert_not_awaited()
        assert isinstance(result, AgentRunResult)
        assert result.output == "Content blocked."

    @pytest.mark.asyncio
    async def test_violation_persists_turn_to_conversation(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
        mock_append_turn: MockType,
    ) -> None:
        """Test that a violation appends the turn to the conversation."""
        mock_client = mocker.Mock()
        mocker.patch(
            f"{_MODULE}.AsyncOgxClientHolder"
        ).return_value.get_client.return_value = mock_client
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(
                "Content blocked.",
                RequestUsage(input_tokens=5, output_tokens=1),
            ),
        )

        config = _make_config()
        guardian = GraniteGuardian(config=config)
        await guardian.wrap_run(mock_ctx, handler=mock_handler)

        mock_append_turn.assert_awaited_once_with(
            mock_client,
            "conv_test",
            "How do I create a pod?",
            "Content blocked.",
        )

    @pytest.mark.asyncio
    async def test_violation_skips_persistence_when_no_conversation_id(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
        mock_append_turn: MockType,
    ) -> None:
        """Test that persistence is skipped without a conversation ID."""
        mock_ctx.model = mocker.Mock(settings={})
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(
                "Content blocked.",
                RequestUsage(input_tokens=5, output_tokens=1),
            ),
        )

        config = _make_config()
        guardian = GraniteGuardian(config=config)
        result = await guardian.wrap_run(mock_ctx, handler=mock_handler)

        mock_append_turn.assert_not_awaited()
        assert result.output == "Content blocked."

    @pytest.mark.asyncio
    async def test_safe_input_does_not_persist_turn(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
        mock_append_turn: MockType,
    ) -> None:
        """Test that a safe input does not touch the conversation."""
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(None, RequestUsage()),
        )

        config = _make_config()
        guardian = GraniteGuardian(config=config)
        await guardian.wrap_run(mock_ctx, handler=mock_handler)

        mock_append_turn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_usage_is_not_accumulated(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that guardian token usage is not added to the run context."""
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(None, RequestUsage(input_tokens=20, output_tokens=5)),
        )

        config = _make_config()
        guardian = GraniteGuardian(config=config)
        await guardian.wrap_run(mock_ctx, handler=mock_handler)

        assert mock_ctx.usage.input_tokens == 0
        assert mock_ctx.usage.output_tokens == 0

    @pytest.mark.asyncio
    async def test_risk_check_failure_propagates(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that wrap_run does not swallow errors from the Guardian endpoint."""
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            side_effect=UnexpectedModelBehavior(
                "No provider_details provided from granite guardian's response"
            ),
        )

        config = _make_config()
        guardian = GraniteGuardian(config=config)

        with pytest.raises(UnexpectedModelBehavior, match="No provider_details"):
            await guardian.wrap_run(mock_ctx, handler=mock_handler)

        mock_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_guardian_unreachable_propagates(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that wrap_run does not swallow connection errors from the Guardian endpoint."""
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            side_effect=ModelAPIError("test", "Connection refused"),
        )

        config = _make_config()
        guardian = GraniteGuardian(config=config)

        with pytest.raises(ModelAPIError, match="Connection refused"):
            await guardian.wrap_run(mock_ctx, handler=mock_handler)

        mock_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_output_violation_from_handler_is_rejected(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that an _OutputGuardrailViolation raised during the run is rejected."""
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(None, RequestUsage()),
        )
        mock_handler.side_effect = _OutputGuardrailViolation("Output blocked.")

        config = _make_config()
        guardian = GraniteGuardian(config=config)
        result = await guardian.wrap_run(mock_ctx, handler=mock_handler)

        assert isinstance(result, AgentRunResult)
        assert result.output == "Output blocked."

    @pytest.mark.asyncio
    async def test_output_violation_replaces_last_assistant_message(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
        mock_append_turn: MockType,
        mock_replace_last_assistant_message: MockType,
    ) -> None:
        """Test that an output violation replaces the already-persisted turn.

        Unlike an input violation, OGX has already recorded a real assistant
        turn by the time an output violation is caught, so the rejection
        should replace that turn rather than append a second one.
        """
        mock_client = mocker.Mock()
        mocker.patch(
            f"{_MODULE}.AsyncOgxClientHolder"
        ).return_value.get_client.return_value = mock_client
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(None, RequestUsage()),
        )
        mock_handler.side_effect = _OutputGuardrailViolation("Output blocked.")

        config = _make_config()
        guardian = GraniteGuardian(config=config)
        await guardian.wrap_run(mock_ctx, handler=mock_handler)

        mock_replace_last_assistant_message.assert_awaited_once_with(
            mock_client,
            "conv_test",
            "Output blocked.",
        )
        mock_append_turn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tool_violation_from_handler_is_rejected(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that a _ToolGuardrailViolation raised during the run is rejected."""
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(None, RequestUsage()),
        )
        mock_handler.side_effect = _ToolGuardrailViolation("Tool output blocked.")

        config = _make_config()
        guardian = GraniteGuardian(config=config)
        result = await guardian.wrap_run(mock_ctx, handler=mock_handler)

        assert isinstance(result, AgentRunResult)
        assert result.output == "Tool output blocked."

    @pytest.mark.asyncio
    async def test_tool_violation_replaces_last_assistant_message(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
        mock_append_turn: MockType,
        mock_replace_last_assistant_message: MockType,
    ) -> None:
        """Test that a tool violation replaces the already-persisted turn.

        By the time a TOOL-point violation is caught, OGX has already
        recorded the model's response requesting the tool call, so the
        rejection should replace that turn rather than append a second one.
        """
        mock_client = mocker.Mock()
        mocker.patch(
            f"{_MODULE}.AsyncOgxClientHolder"
        ).return_value.get_client.return_value = mock_client
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(None, RequestUsage()),
        )
        mock_handler.side_effect = _ToolGuardrailViolation("Tool output blocked.")

        config = _make_config()
        guardian = GraniteGuardian(config=config)
        await guardian.wrap_run(mock_ctx, handler=mock_handler)

        mock_replace_last_assistant_message.assert_awaited_once_with(
            mock_client,
            "conv_test",
            "Tool output blocked.",
        )
        mock_append_turn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tool_violation_preserves_tool_call_in_result(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_handler: MockType,
    ) -> None:
        """Test that a tool violation's preserved parts survive into the result.

        The offending tool call (and its result) carried on the
        ``_ToolGuardrailViolation`` should end up in the rejection's message
        history, so ``tool_calls``/``tool_results`` built from it still show
        what was actually called even though the answer text is replaced.
        """
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(None, RequestUsage()),
        )
        call = ToolCallPart(
            tool_name="descriptive_stats", args={}, tool_call_id="call_1"
        )
        return_part = ToolReturnPart(
            tool_name="descriptive_stats",
            content="malicious output",
            tool_call_id="call_1",
        )
        mock_handler.side_effect = _ToolGuardrailViolation(
            "Tool output blocked.",
            response_parts=(call,),
            request_parts=(return_part,),
        )

        config = _make_config()
        guardian = GraniteGuardian(config=config)
        result = await guardian.wrap_run(mock_ctx, handler=mock_handler)

        assert isinstance(result, AgentRunResult)
        assert result.output == "Tool output blocked."
        new_messages = result.new_messages()
        tool_calls = [
            part
            for message in new_messages
            if hasattr(message, "parts")
            for part in message.parts
            if isinstance(part, ToolCallPart)
        ]
        tool_returns = [
            part
            for message in new_messages
            if hasattr(message, "parts")
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        assert tool_calls == [call]
        assert tool_returns == [return_part]


class TestGraniteGuardianAfterToolExecute:
    """Tests for GraniteGuardian.after_tool_execute."""

    @pytest.fixture(autouse=True)
    def _mock_init(self, mocker: MockerFixture) -> None:
        """Mock model creation and clear cache for all tests."""
        GraniteGuardian._model_cache.clear()
        mocker.patch(f"{_MODULE}.httpx.AsyncClient")
        mocker.patch(f"{_MODULE}.AsyncOpenAI")
        mocker.patch(f"{_MODULE}.OpenAIProvider")
        mocker.patch(f"{_MODULE}.OpenAIChatModel")

    @pytest.fixture(name="mock_ctx")
    def mock_ctx_fixture(self, mocker: MockerFixture) -> RunContext:
        """Create a mock RunContext."""
        return mocker.Mock(spec=RunContext)

    @pytest.fixture(name="mock_call")
    def mock_call_fixture(self) -> ToolCallPart:
        """Create a real ToolCallPart (needed for tool_name/tool_call_id access)."""
        return ToolCallPart(tool_name="test_tool", args={}, tool_call_id="call_1")

    @pytest.fixture(name="mock_tool_def")
    def mock_tool_def_fixture(self, mocker: MockerFixture) -> ToolDefinition:
        """Create a mock ToolDefinition."""
        return mocker.Mock(spec=ToolDefinition)

    @pytest.mark.asyncio
    async def test_passes_through_when_no_tool_guardrails(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_call: ToolCallPart,
        mock_tool_def: ToolDefinition,
    ) -> None:
        """Test the result passes through unchanged with no TOOL-point risks."""
        mock_run_risk_check = mocker.patch(f"{_MODULE}._run_risk_check")

        config = _make_config(risks=[_make_risk(points=["input"])])
        guardian = GraniteGuardian(config=config)
        result = await guardian.after_tool_execute(
            mock_ctx,
            call=mock_call,
            tool_def=mock_tool_def,
            args={},
            result="tool output",
        )

        assert result == "tool output"
        mock_run_risk_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_safe_result_passes_through(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_call: ToolCallPart,
        mock_tool_def: ToolDefinition,
    ) -> None:
        """Test that a safe tool result passes through unchanged."""
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(None, RequestUsage()),
        )

        config = _make_config(risks=[_make_risk(points=["tool"])])
        guardian = GraniteGuardian(config=config)
        result = await guardian.after_tool_execute(
            mock_ctx,
            call=mock_call,
            tool_def=mock_tool_def,
            args={},
            result="tool output",
        )

        assert result == "tool output"

    @pytest.mark.asyncio
    async def test_violation_raises_tool_guardrail_violation(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_call: ToolCallPart,
        mock_tool_def: ToolDefinition,
    ) -> None:
        """Test that a violated TOOL-point risk raises _ToolGuardrailViolation."""
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=("Tool content blocked.", RequestUsage()),
        )

        config = _make_config(risks=[_make_risk(points=["tool"])])
        guardian = GraniteGuardian(config=config)

        with pytest.raises(
            _ToolGuardrailViolation, match="Tool content blocked."
        ) as exc_info:
            await guardian.after_tool_execute(
                mock_ctx,
                call=mock_call,
                tool_def=mock_tool_def,
                args={},
                result="malicious output",
            )

        # The tool call is preserved so tool_calls still shows it, but the
        # result -- the flagged content -- is never preserved: tool_results
        # must not expose it.
        assert exc_info.value.response_parts == (mock_call,)
        assert exc_info.value.request_parts == ()

    @pytest.mark.asyncio
    async def test_non_string_result_is_rendered_before_check(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_call: ToolCallPart,
        mock_tool_def: ToolDefinition,
    ) -> None:
        """Test that a non-string result is rendered to text before checking."""
        mock_run_risk_check = mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(None, RequestUsage()),
        )

        config = _make_config(risks=[_make_risk(points=["tool"])])
        guardian = GraniteGuardian(config=config)
        await guardian.after_tool_execute(
            mock_ctx,
            call=mock_call,
            tool_def=mock_tool_def,
            args={},
            result={"a": 1},
        )

        mock_run_risk_check.assert_awaited_once()
        assert mock_run_risk_check.call_args[0][0] == '{"a": 1}'


class TestGraniteGuardianRun:
    """Tests for GraniteGuardian.run (standalone shield interface)."""

    @pytest.fixture(autouse=True)
    def _mock_init(self, mocker: MockerFixture) -> None:
        """Mock model creation and clear cache for all tests."""
        GraniteGuardian._model_cache.clear()
        mocker.patch(f"{_MODULE}.httpx.AsyncClient")
        mocker.patch(f"{_MODULE}.AsyncOpenAI")
        mocker.patch(f"{_MODULE}.OpenAIProvider")
        mocker.patch(f"{_MODULE}.OpenAIChatModel")

    @pytest.mark.asyncio
    async def test_returns_passed_when_safe(self, mocker: MockerFixture) -> None:
        """Test that a safe input returns ShieldModerationPassed."""
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(None, RequestUsage()),
        )

        config = _make_config()
        guardian = GraniteGuardian(config=config)
        result = await guardian.run("safe text")

        assert isinstance(result, ShieldModerationPassed)

    @pytest.mark.asyncio
    async def test_returns_blocked_on_violation(self, mocker: MockerFixture) -> None:
        """Test that a violation returns ShieldModerationBlocked."""
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=("Content blocked.", RequestUsage()),
        )

        config = _make_config()
        guardian = GraniteGuardian(config=config)
        result = await guardian.run("harmful text")

        assert isinstance(result, ShieldModerationBlocked)
        assert result.message == "Content blocked."

    @pytest.mark.asyncio
    async def test_uses_run_moderation_guardrail_point(
        self, mocker: MockerFixture
    ) -> None:
        """Test that run() filters by run_moderation_guardrail_point."""
        mock_filter = mocker.patch(f"{_MODULE}._filter_guardrails", return_value=[])
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(None, RequestUsage()),
        )

        config = _make_config()
        guardian = GraniteGuardian(
            config=config, run_moderation_guardrail_point="output"
        )
        await guardian.run("some text")

        mock_filter.assert_called_once_with(config.risks, "output")

    @pytest.mark.asyncio
    async def test_blocked_result_has_moderation_id(
        self, mocker: MockerFixture
    ) -> None:
        """Test that blocked results include a moderation ID."""
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=("Blocked.", RequestUsage()),
        )

        config = _make_config()
        guardian = GraniteGuardian(config=config)
        result = await guardian.run("bad text")

        assert isinstance(result, ShieldModerationBlocked)
        assert result.moderation_id.startswith("modr-")

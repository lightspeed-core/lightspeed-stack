"""Unit tests for safety.granite_guardian.capability."""

import math
from typing import Any

import pytest
from pydantic_ai import AgentRunResult
from pydantic_ai.exceptions import SkipModelRequest, UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.tools import ToolDefinition
from pytest_mock import MockerFixture

from safety.exceptions import ToolBlocked
from safety.granite_guardian.capability import GraniteGuardian, GraniteGuardianRisk
from safety.granite_guardian.types import DEFAULT_VIOLATION_MESSAGE, Risk
from safety.types import GuardrailResult
from tests.unit.safety.helpers import request_context, run_context

_MODULE = "safety.granite_guardian.capability"


def _risk(**overrides: Any) -> Risk:
    """Build a risk with harmless defaults."""
    values: dict[str, Any] = {
        "name": "harm",
        "criteria": "harmful content",
        "violation_message": "Blocked.",
        "threshold": 0.5,
        "type": ["input"],
    }
    values.update(overrides)
    return Risk(**values)


def _score_logprobs(risky: float) -> list[dict[str, Any]]:
    """Build logprobs whose risky probability is `risky`."""
    safe = 1.0 - risky
    return [
        {"token": "<think>", "logprob": 0.0, "bytes": None, "top_logprobs": []},
        {"token": "\n", "logprob": 0.0, "bytes": None, "top_logprobs": []},
        {"token": "</think>", "logprob": 0.0, "bytes": None, "top_logprobs": []},
        {"token": "<score>", "logprob": 0.0, "bytes": None, "top_logprobs": []},
        {
            "token": "no",
            "logprob": math.log(safe),
            "bytes": None,
            "top_logprobs": [
                {"token": "no", "logprob": math.log(safe), "bytes": None},
                {"token": "yes", "logprob": math.log(risky), "bytes": None},
            ],
        },
        {"token": "</score>", "logprob": 0.0, "bytes": None, "top_logprobs": []},
    ]


def _response(provider_details: dict[str, Any] | None) -> ModelResponse:
    """Build a model response carrying Granite Guardian provider details."""
    return ModelResponse(
        parts=[TextPart(content="score")],
        provider_details=provider_details,
    )


def _patch_request(mocker: MockerFixture, provider_details: dict[str, Any] | None):
    """Patch the Granite Guardian model call to return `provider_details`."""
    return mocker.patch(
        f"{_MODULE}.model_request",
        new_callable=mocker.AsyncMock,
        return_value=_response(provider_details),
    )


class TestGraniteGuardianRiskEvaluate:
    """Tests for GraniteGuardianRisk.evaluate."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("risky", "threshold", "expected"),
        [
            (0.2, 0.5, GuardrailResult.allow()),
            (0.8, 0.5, GuardrailResult.block(message="Blocked.")),
            (0.5, 0.5, GuardrailResult.block(message="Blocked.")),
            (0.5, 0.51, GuardrailResult.allow()),
        ],
    )
    async def test_compares_the_risky_probability_with_the_threshold(
        self,
        mocker: MockerFixture,
        risky: float,
        threshold: float,
        expected: GuardrailResult,
    ) -> None:
        """Test that the risk threshold decides allow and block."""
        _patch_request(mocker, {"logprobs": _score_logprobs(risky)})
        capability = GraniteGuardianRisk(
            risk=_risk(threshold=threshold),
            model=mocker.Mock(),
        )

        assert await capability.evaluate("hello") == expected

    @pytest.mark.asyncio
    async def test_uses_the_default_violation_message(
        self, mocker: MockerFixture
    ) -> None:
        """Test that a risk without its own message uses the generic one."""
        _patch_request(mocker, {"logprobs": _score_logprobs(0.9)})
        capability = GraniteGuardianRisk(
            risk=Risk(
                name="harm",
                criteria="harmful content",
                threshold=0.5,
                type=["input"],
            ),
            model=mocker.Mock(),
        )

        result = await capability.evaluate("hello")

        assert result == GuardrailResult.block(message=DEFAULT_VIOLATION_MESSAGE)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("think", "expected_preamble", "absent"),
        [
            (False, "<guardian><no-think>", None),
            (True, "<guardian><think>", "<no-think>"),
        ],
    )
    async def test_sends_the_risk_criteria_and_logprob_settings(
        self,
        mocker: MockerFixture,
        think: bool,
        expected_preamble: str,
        absent: str | None,
    ) -> None:
        """Test that the check asks Granite Guardian to score this risk."""
        model = mocker.Mock()
        mock_request = _patch_request(mocker, {"logprobs": _score_logprobs(0.1)})
        capability = GraniteGuardianRisk(
            risk=_risk(criteria="harmful content", enable_thinking=think),
            model=model,
        )

        await capability.evaluate("the prompt")

        kwargs = mock_request.await_args.kwargs
        assert kwargs["model"] is model
        assert kwargs["model_settings"] == {
            "openai_logprobs": True,
            "openai_top_logprobs": 20,
        }
        message = kwargs["messages"][0]
        assert isinstance(message, ModelRequest)
        assert message.instructions is not None
        assert expected_preamble in message.instructions
        assert "### Criteria: harmful content" in message.instructions
        if absent is not None:
            assert absent not in message.instructions
        user = message.parts[0]
        assert isinstance(user, UserPromptPart)
        assert user.content == "the prompt"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("details", [None, {}])
    async def test_missing_provider_details(
        self,
        mocker: MockerFixture,
        details: dict[str, Any] | None,
    ) -> None:
        """Test that a response without provider details is an error."""
        _patch_request(mocker, details)
        capability = GraniteGuardianRisk(risk=_risk(), model=mocker.Mock())

        with pytest.raises(UnexpectedModelBehavior, match="No provider_details"):
            await capability.evaluate("hello")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "details",
        [{"other": True}, {"logprobs": []}, {"logprobs": None}],
    )
    async def test_missing_logprobs(
        self,
        mocker: MockerFixture,
        details: dict[str, Any],
    ) -> None:
        """Test that provider details without usable logprobs are an error."""
        _patch_request(mocker, details)
        capability = GraniteGuardianRisk(risk=_risk(), model=mocker.Mock())

        with pytest.raises(UnexpectedModelBehavior, match="No logprobs"):
            await capability.evaluate("hello")

    @pytest.mark.asyncio
    async def test_malformed_logprobs_propagate(self, mocker: MockerFixture) -> None:
        """Test that a score which is not in the expected format is an error."""
        _patch_request(
            mocker,
            {
                "logprobs": [
                    {
                        "token": "plain",
                        "logprob": 0.0,
                        "bytes": None,
                        "top_logprobs": [],
                    }
                ]
            },
        )
        capability = GraniteGuardianRisk(risk=_risk(), model=mocker.Mock())

        with pytest.raises(UnexpectedModelBehavior, match="did not generate"):
            await capability.evaluate("hello")

    @pytest.mark.asyncio
    async def test_model_errors_propagate(self, mocker: MockerFixture) -> None:
        """Test that a failed model call is not turned into a verdict."""
        mocker.patch(
            f"{_MODULE}.model_request",
            new_callable=mocker.AsyncMock,
            side_effect=RuntimeError("down"),
        )
        capability = GraniteGuardianRisk(risk=_risk(), model=mocker.Mock())

        with pytest.raises(RuntimeError, match="down"):
            await capability.evaluate("hello")


class TestGraniteGuardian:
    """Tests for GraniteGuardian construction."""

    def test_copies_guard_points_from_the_risk(self, mocker: MockerFixture) -> None:
        """Test that a risk capability screens the points configured on its risk."""
        risk = _risk(type=["output"])
        capability = GraniteGuardianRisk(risk=risk, model=mocker.Mock())

        assert capability.type == ["output"]
        assert capability.risk is risk

    def test_builds_one_child_per_risk(self, mocker: MockerFixture) -> None:
        """Test that each risk becomes its own guard sharing the model."""
        model = mocker.Mock()
        harm = _risk(name="harm", criteria="harmful", type=["input"])
        jailbreak = _risk(
            name="jailbreak",
            criteria="injection",
            type=["output", "tool"],
            enable_thinking=True,
        )
        guardian = GraniteGuardian(  # pylint: disable=unexpected-keyword-arg
            risks=[harm, jailbreak],
            model=model,
            check_tokens=7,
            id="shield",
        )

        assert len(guardian.capabilities) == 2
        harm_guard, jailbreak_guard = guardian.capabilities
        assert isinstance(harm_guard, GraniteGuardianRisk)
        assert isinstance(jailbreak_guard, GraniteGuardianRisk)
        assert harm_guard.id == "shield.harm"
        assert jailbreak_guard.id == "shield.jailbreak"
        assert harm_guard.model is model
        assert jailbreak_guard.model is model
        assert harm_guard.check_tokens == 7
        assert jailbreak_guard.check_tokens == 7
        assert harm_guard.type == ["input"]
        assert jailbreak_guard.type == ["output", "tool"]
        assert harm_guard.risk is harm
        assert jailbreak_guard.risk.enable_thinking is True

    def test_omitted_id_uses_the_risk_name(self, mocker: MockerFixture) -> None:
        """Test that a shield without an id names each child after its risk."""
        guardian = GraniteGuardian(risks=[_risk(name="harm")], model=mocker.Mock())

        assert guardian.capabilities[0].id == "harm"

    def test_empty_risks_and_default_check_interval(
        self, mocker: MockerFixture
    ) -> None:
        """Test that a shield with no risks has no children."""
        guardian = GraniteGuardian(risks=[], model=mocker.Mock())

        assert guardian.capabilities == []
        assert guardian.check_tokens == 50


class TestGraniteGuardianRiskHooks:
    """Tests for a Granite Guardian risk wired through the safety hooks."""

    @pytest.mark.asyncio
    async def test_safe_input_reaches_the_handler(self, mocker: MockerFixture) -> None:
        """Test that a safe prompt is forwarded to the model request."""
        mock_request = _patch_request(mocker, {"logprobs": _score_logprobs(0.1)})
        capability = GraniteGuardianRisk(risk=_risk(), model=mocker.Mock())
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
        assert isinstance(response.parts[0], TextPart)
        assert response.parts[0].content == "ok"
        screened = mock_request.await_args.kwargs["messages"][0].parts[0]
        assert isinstance(screened, UserPromptPart)
        assert screened.content == "How do I restart a node?"

    @pytest.mark.asyncio
    async def test_unsafe_input_skips_the_model_request(
        self, mocker: MockerFixture
    ) -> None:
        """Test that an unsafe prompt is replaced by the violation message."""
        _patch_request(mocker, {"logprobs": _score_logprobs(0.9)})
        capability = GraniteGuardianRisk(risk=_risk(), model=mocker.Mock())
        messages = [ModelRequest(parts=[UserPromptPart(content="do harm")])]
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
        assert part.content == "Blocked."

    @pytest.mark.asyncio
    async def test_unsafe_output_replaces_the_run_result(
        self, mocker: MockerFixture
    ) -> None:
        """Test that an unsafe final answer is replaced by the violation message."""
        _patch_request(mocker, {"logprobs": _score_logprobs(0.9)})
        capability = GraniteGuardianRisk(
            risk=_risk(type=["output"]),
            model=mocker.Mock(),
        )
        result = AgentRunResult(output="harmful answer")

        async def _handler() -> AgentRunResult[str]:
            return result

        returned = await capability.wrap_run(run_context(), handler=_handler)

        assert returned.output == "Blocked."
        assert result.output == "harmful answer"

    @pytest.mark.asyncio
    async def test_unsafe_tool_result_raises(self, mocker: MockerFixture) -> None:
        """Test that an unsafe tool result aborts the run."""
        _patch_request(mocker, {"logprobs": _score_logprobs(0.9)})
        capability = GraniteGuardianRisk(
            risk=_risk(type=["tool"]),
            model=mocker.Mock(),
        )

        with pytest.raises(ToolBlocked) as exc_info:
            await capability.after_tool_execute(
                run_context(),
                call=ToolCallPart("lookup", {"q": "x"}),
                tool_def=ToolDefinition(name="lookup"),
                args={"q": "x"},
                result="harmful tool output",
            )

        assert exc_info.value.reason == "Blocked."

    @pytest.mark.asyncio
    async def test_output_risk_does_not_screen_input(
        self, mocker: MockerFixture
    ) -> None:
        """Test that a risk limited to output does not classify the user prompt."""
        mock_request = _patch_request(mocker, {"logprobs": _score_logprobs(0.9)})
        capability = GraniteGuardianRisk(
            risk=_risk(type=["output"]),
            model=mocker.Mock(),
        )
        messages = [ModelRequest(parts=[UserPromptPart(content="hello")])]

        async def _handler(_request_context: ModelRequestContext) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="ok")])

        response = await capability.wrap_model_request(
            run_context(),
            request_context=request_context(messages),
            handler=_handler,
        )

        mock_request.assert_not_awaited()
        assert isinstance(response.parts[0], TextPart)
        assert response.parts[0].content == "ok"

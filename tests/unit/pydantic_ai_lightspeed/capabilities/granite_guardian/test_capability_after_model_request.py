"""Unit tests for GraniteGuardian.after_model_request (native tool guardrails).

Native tools (e.g. MCP server tools) can be executed by the OGX backend
itself as part of a single model response, so their results never pass
through pydantic-ai's own tool-execution machinery and never reach
``after_tool_execute``. ``after_model_request`` closes that gap by
screening ``NativeToolReturnPart`` results embedded directly in the
response.
"""

# pylint: disable=protected-access

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelResponse, NativeToolCallPart, NativeToolReturnPart
from pydantic_ai.usage import RequestUsage
from pytest_mock import MockerFixture, MockType

from pydantic_ai_lightspeed.capabilities.granite_guardian._capability import (
    GraniteGuardian,
    _ToolGuardrailViolation,
)

from .test_capability import _make_config, _make_risk

_MODULE = "pydantic_ai_lightspeed.capabilities.granite_guardian._capability"


def _response_with_native_tool_call(
    content: object = "mcp tool output",
) -> ModelResponse:
    """Build a ModelResponse containing one resolved native tool call/return pair."""
    return ModelResponse(
        parts=[
            NativeToolCallPart(
                tool_name="mcp_server:test-mcp-server",
                args={"tool_name": "descriptive_stats"},
                tool_call_id="call_1",
            ),
            NativeToolReturnPart(
                tool_name="mcp_server:test-mcp-server",
                content=content,
                tool_call_id="call_1",
            ),
        ]
    )


class TestGraniteGuardianAfterModelRequest:
    """Tests for GraniteGuardian.after_model_request."""

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

    @pytest.fixture(name="mock_request_context")
    def mock_request_context_fixture(self, mocker: MockerFixture) -> MockType:
        """Create a mock ModelRequestContext."""
        return mocker.Mock()

    @pytest.mark.asyncio
    async def test_passes_through_when_no_tool_guardrails(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_request_context: MockType,
    ) -> None:
        """Test the response passes through unchanged with no TOOL-point risks."""
        mock_run_risk_check = mocker.patch(f"{_MODULE}._run_risk_check")

        config = _make_config(risks=[_make_risk(points=["input"])])
        guardian = GraniteGuardian(config=config)
        response = _response_with_native_tool_call()
        result = await guardian.after_model_request(
            mock_ctx, request_context=mock_request_context, response=response
        )

        assert result is response
        mock_run_risk_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_through_when_no_native_tool_calls(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_request_context: MockType,
    ) -> None:
        """Test the response passes through unchanged when it has no native tool calls."""
        mock_run_risk_check = mocker.patch(f"{_MODULE}._run_risk_check")

        config = _make_config(risks=[_make_risk(points=["tool"])])
        guardian = GraniteGuardian(config=config)
        response = ModelResponse(parts=[])
        result = await guardian.after_model_request(
            mock_ctx, request_context=mock_request_context, response=response
        )

        assert result is response
        mock_run_risk_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_safe_native_tool_result_passes_through(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_request_context: MockType,
    ) -> None:
        """Test that a safe native tool result passes through unchanged."""
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(None, RequestUsage()),
        )

        config = _make_config(risks=[_make_risk(points=["tool"])])
        guardian = GraniteGuardian(config=config)
        response = _response_with_native_tool_call()
        result = await guardian.after_model_request(
            mock_ctx, request_context=mock_request_context, response=response
        )

        assert result is response

    @pytest.mark.asyncio
    async def test_violation_raises_tool_guardrail_violation(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_request_context: MockType,
    ) -> None:
        """Test that a violated TOOL-point risk on a native tool result raises.

        This covers the MCP-call scenario from the bug report: OGX resolves
        the MCP tool call server-side and returns the result already embedded
        in the model response, so this is the only hook that can screen it.
        """
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=("Tool content blocked.", RequestUsage()),
        )

        config = _make_config(risks=[_make_risk(points=["tool"])])
        guardian = GraniteGuardian(config=config)
        response = _response_with_native_tool_call(content="malicious output")

        with pytest.raises(
            _ToolGuardrailViolation, match="Tool content blocked."
        ) as exc_info:
            await guardian.after_model_request(
                mock_ctx, request_context=mock_request_context, response=response
            )

        # The native call is preserved so tool_calls still shows it, but a
        # fresh, content-stripped, denied return part stands in for the
        # real one -- the flagged content must never reach tool_results.
        response_parts = exc_info.value.response_parts
        assert len(response_parts) == 2
        call_part, return_part = response_parts
        assert isinstance(call_part, NativeToolCallPart)
        assert call_part is response.parts[0]
        assert isinstance(return_part, NativeToolReturnPart)
        assert return_part is not response.parts[1]
        assert return_part.content == {}
        assert return_part.outcome == "denied"
        assert return_part.tool_call_id == "call_1"
        assert exc_info.value.request_parts == ()

    @pytest.mark.asyncio
    async def test_violation_preserves_preceding_safe_native_results(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_request_context: MockType,
    ) -> None:
        """Test that a safe pair *before* the violation keeps its result.

        Regression test for a bug where a response with multiple native
        tool call/return pairs had *every* result blanked out on a
        violation, even results from a call that never violated any risk.
        """
        mocker.patch(
            f"{_MODULE}._run_risk_check",
            side_effect=[
                (None, RequestUsage()),
                ("Tool content blocked.", RequestUsage()),
            ],
        )

        config = _make_config(risks=[_make_risk(points=["tool"])])
        guardian = GraniteGuardian(config=config)
        response = ModelResponse(
            parts=[
                NativeToolCallPart(
                    tool_name="mcp_server:test-mcp-server",
                    args={"tool_name": "get_weather"},
                    tool_call_id="call_safe",
                ),
                NativeToolReturnPart(
                    tool_name="mcp_server:test-mcp-server",
                    content="safe weather output",
                    tool_call_id="call_safe",
                ),
                NativeToolCallPart(
                    tool_name="mcp_server:test-mcp-server",
                    args={"tool_name": "descriptive_stats"},
                    tool_call_id="call_1",
                ),
                NativeToolReturnPart(
                    tool_name="mcp_server:test-mcp-server",
                    content="malicious output",
                    tool_call_id="call_1",
                ),
            ]
        )

        with pytest.raises(
            _ToolGuardrailViolation, match="Tool content blocked."
        ) as exc_info:
            await guardian.after_model_request(
                mock_ctx, request_context=mock_request_context, response=response
            )

        response_parts = exc_info.value.response_parts
        assert len(response_parts) == 4
        safe_call, safe_return, denied_call, denied_return = response_parts

        # The safe pair is preserved exactly as-is.
        assert safe_call is response.parts[0]
        assert safe_return is response.parts[1]

        # The violating pair's call is preserved, but its result is a fresh,
        # content-stripped, denied placeholder -- never the real content.
        assert denied_call is response.parts[2]
        assert isinstance(denied_return, NativeToolReturnPart)
        assert denied_return is not response.parts[3]
        assert denied_return.content == {}
        assert denied_return.outcome == "denied"
        assert denied_return.tool_call_id == "call_1"

    @pytest.mark.asyncio
    async def test_violation_also_denies_later_native_results(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_request_context: MockType,
    ) -> None:
        """Test that results *after* the first violation are denied too.

        Once one native tool result is flagged, later results in the same
        response are treated as suspect and withheld too -- even a later
        pair whose own content would otherwise pass the risk check -- since
        it's checked at most once and never evaluated after a violation.
        """
        mock_run_risk_check = mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=("Tool content blocked.", RequestUsage()),
        )

        config = _make_config(risks=[_make_risk(points=["tool"])])
        guardian = GraniteGuardian(config=config)
        response = ModelResponse(
            parts=[
                NativeToolCallPart(
                    tool_name="mcp_server:test-mcp-server",
                    args={"tool_name": "descriptive_stats"},
                    tool_call_id="call_1",
                ),
                NativeToolReturnPart(
                    tool_name="mcp_server:test-mcp-server",
                    content="malicious output",
                    tool_call_id="call_1",
                ),
                NativeToolCallPart(
                    tool_name="mcp_server:test-mcp-server",
                    args={"tool_name": "get_weather"},
                    tool_call_id="call_after",
                ),
                NativeToolReturnPart(
                    tool_name="mcp_server:test-mcp-server",
                    content="otherwise-safe weather output",
                    tool_call_id="call_after",
                ),
            ]
        )

        with pytest.raises(
            _ToolGuardrailViolation, match="Tool content blocked."
        ) as exc_info:
            await guardian.after_model_request(
                mock_ctx, request_context=mock_request_context, response=response
            )

        response_parts = exc_info.value.response_parts
        assert len(response_parts) == 4
        first_call, first_return, later_call, later_return = response_parts

        assert first_call is response.parts[0]
        assert isinstance(first_return, NativeToolReturnPart)
        assert first_return.outcome == "denied"
        assert first_return.content == {}

        # The later pair's call is preserved, but its result is denied too,
        # even though it was never individually risk-checked.
        assert later_call is response.parts[2]
        assert isinstance(later_return, NativeToolReturnPart)
        assert later_return is not response.parts[3]
        assert later_return.content == {}
        assert later_return.outcome == "denied"
        assert later_return.tool_call_id == "call_after"

        # Only the first (violating) pair's content was ever checked.
        mock_run_risk_check.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mcp_list_tools_call_is_never_evaluated(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_request_context: MockType,
    ) -> None:
        """Test that an MCP ``list_tools`` discovery call is never risk-checked.

        ``list_tools`` calls just enumerate what an MCP server offers -- they
        carry no user-supplied or tool-produced content, so they should never
        be evaluated by (or blocked by) a TOOL-point risk, no matter what
        their content looks like.
        """
        mock_run_risk_check = mocker.patch(f"{_MODULE}._run_risk_check")

        config = _make_config(risks=[_make_risk(points=["tool"])])
        guardian = GraniteGuardian(config=config)
        response = ModelResponse(
            parts=[
                NativeToolCallPart(
                    tool_name="mcp_server:test-mcp-server",
                    args={"action": "list_tools", "server_label": "test-mcp-server"},
                    tool_call_id="call_list",
                ),
                NativeToolReturnPart(
                    tool_name="mcp_server:test-mcp-server",
                    content="anything at all, even flagged-looking content",
                    tool_call_id="call_list",
                ),
            ]
        )

        result = await guardian.after_model_request(
            mock_ctx, request_context=mock_request_context, response=response
        )

        assert result is response
        mock_run_risk_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_string_content_is_rendered_before_check(
        self,
        mocker: MockerFixture,
        mock_ctx: RunContext,
        mock_request_context: MockType,
    ) -> None:
        """Test that non-string native tool content is rendered to text before checking."""
        mock_run_risk_check = mocker.patch(
            f"{_MODULE}._run_risk_check",
            return_value=(None, RequestUsage()),
        )

        config = _make_config(risks=[_make_risk(points=["tool"])])
        guardian = GraniteGuardian(config=config)
        response = _response_with_native_tool_call(content={"output": 1})
        await guardian.after_model_request(
            mock_ctx, request_context=mock_request_context, response=response
        )

        mock_run_risk_check.assert_awaited_once()
        assert mock_run_risk_check.call_args[0][0] == '{"output": 1}'

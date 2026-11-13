"""Unit tests for safety.redaction.capability."""

import re

import pytest
from pydantic_ai import AgentRunResult
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.tools import ToolDefinition

from safety.redaction.capability import DEFAULT_REPLACEMENT, RedactionCapability
from safety.types import GuardrailResult
from tests.unit.safety.helpers import request_context, run_context

_EMAIL = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"


def _email_guard(**overrides: object) -> RedactionCapability:
    """Return a redaction guard for email addresses."""
    kwargs: dict[str, object] = {"patterns": {"email": _EMAIL}}
    kwargs.update(overrides)
    return RedactionCapability(**kwargs)  # type: ignore[arg-type]


class TestRedactionInit:
    """Tests for RedactionCapability construction."""

    def test_none_fields_use_module_defaults(self) -> None:
        """Test that omitted patterns and replacement fall back to defaults."""
        capability = RedactionCapability(patterns=None, replacement=None)

        assert capability.patterns == {}
        assert capability.replacement == DEFAULT_REPLACEMENT
        assert list(capability.type) == ["input"]

    def test_custom_fields_are_kept(self) -> None:
        """Test that explicit patterns, replacement, and guard points are kept."""
        patterns = {"digits": r"\d+"}
        capability = RedactionCapability(
            patterns=patterns,
            replacement="X",
            type=["output"],
        )

        assert capability.patterns is patterns
        assert capability.replacement == "X"
        assert list(capability.type) == ["output"]

    def test_invalid_pattern_fails_at_init(self) -> None:
        """Test that a pattern is compiled while the capability is constructed."""
        with pytest.raises(re.error):
            RedactionCapability(patterns={"bad": "("})


class TestRedactionEvaluate:
    """Tests for RedactionCapability.evaluate."""

    @pytest.mark.asyncio
    async def test_no_patterns_allows_the_text(self) -> None:
        """Test that a guard with no patterns leaves text unchanged."""
        result = await RedactionCapability().evaluate("a@b.co")

        assert result == GuardrailResult.allow()

    @pytest.mark.asyncio
    async def test_no_match_allows_the_text(self) -> None:
        """Test that a miss does not produce a replace verdict."""
        result = await _email_guard().evaluate("no address here")

        assert result == GuardrailResult.allow()

    @pytest.mark.asyncio
    async def test_replaces_every_match(self) -> None:
        """Test that each match of a pattern is replaced."""
        result = await _email_guard().evaluate("mail a@b.co and c@d.co")

        assert result == GuardrailResult.replace(
            f"mail {DEFAULT_REPLACEMENT} and {DEFAULT_REPLACEMENT}"
        )

    @pytest.mark.asyncio
    async def test_applies_every_configured_pattern(self) -> None:
        """Test that each configured pattern is applied to the text."""
        capability = RedactionCapability(
            patterns={"email": _EMAIL, "digits": r"\d+"},
        )

        result = await capability.evaluate("a@b.co 12")

        assert result == GuardrailResult.replace(
            f"{DEFAULT_REPLACEMENT} {DEFAULT_REPLACEMENT}"
        )

    @pytest.mark.asyncio
    async def test_patterns_run_in_mapping_order(self) -> None:
        """Test that a later pattern sees the earlier pattern's replacement."""
        capability = RedactionCapability(
            patterns={"word": r"secret", "marker": r"HIDDEN"},
            replacement="HIDDEN!",
        )

        result = await capability.evaluate("secret")

        assert result == GuardrailResult.replace("HIDDEN!!")

    @pytest.mark.asyncio
    async def test_patterns_added_after_init_are_ignored(self) -> None:
        """Test that patterns are compiled once, during construction."""
        patterns = {"word": r"secret"}
        capability = RedactionCapability(patterns=patterns)
        patterns["extra"] = r"extra"

        result = await capability.evaluate("extra secret")

        assert result == GuardrailResult.replace(f"extra {DEFAULT_REPLACEMENT}")

    @pytest.mark.asyncio
    async def test_matching_is_case_sensitive(self) -> None:
        """Test that a pattern does not match a different case."""
        capability = RedactionCapability(patterns={"word": r"secret"})

        result = await capability.evaluate("SECRET")

        assert result == GuardrailResult.allow()

    @pytest.mark.asyncio
    async def test_empty_replacement_falls_back_to_the_default(self) -> None:
        """Test that a falsy replacement uses the module default at evaluate time."""
        capability = RedactionCapability(patterns={"digits": r"\d+"})
        capability.replacement = ""

        result = await capability.evaluate("a1")

        assert result == GuardrailResult.replace(f"a{DEFAULT_REPLACEMENT}")


class TestRedactionHooks:
    """Tests for redaction wired through the safety capability hooks."""

    @pytest.mark.asyncio
    async def test_wrap_model_request_redacts_the_latest_prompt(self) -> None:
        """Test that an input guard rewrites the latest user prompt in place."""
        capability = _email_guard()
        earlier = ModelRequest(parts=[UserPromptPart(content="keep a@b.co")])
        latest = ModelRequest(parts=[UserPromptPart(content="mail a@b.co")])
        messages = [earlier, latest]
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
        assert earlier.parts[0].content == "keep a@b.co"
        assert latest.parts[0].content == f"mail {DEFAULT_REPLACEMENT}"
        assert isinstance(response.parts[0], TextPart)
        assert response.parts[0].content == "ok"

    @pytest.mark.asyncio
    async def test_wrap_model_request_leaves_a_clean_prompt(self) -> None:
        """Test that a prompt with no match is not rewritten."""
        capability = _email_guard()
        messages = [ModelRequest(parts=[UserPromptPart(content="hello")])]

        async def _handler(_request_context: ModelRequestContext) -> ModelResponse:
            return ModelResponse(parts=[TextPart(content="ok")])

        await capability.wrap_model_request(
            run_context(),
            request_context=request_context(messages),
            handler=_handler,
        )

        assert messages[0].parts[0].content == "hello"

    @pytest.mark.asyncio
    async def test_default_type_does_not_redact_final_output(self) -> None:
        """Test that the default guard points do not screen model output."""
        capability = _email_guard()
        result = AgentRunResult(output="mail a@b.co")

        async def _handler() -> AgentRunResult[str]:
            return result

        returned = await capability.wrap_run(run_context(), handler=_handler)

        assert returned is result
        assert returned.output == "mail a@b.co"

    @pytest.mark.asyncio
    async def test_output_guard_redacts_the_final_result(self) -> None:
        """Test that an output guard replaces the run result without mutating it."""
        capability = _email_guard(type=["output"])
        result = AgentRunResult(output="mail a@b.co")

        async def _handler() -> AgentRunResult[str]:
            return result

        returned = await capability.wrap_run(run_context(), handler=_handler)

        assert returned is not result
        assert returned.output == f"mail {DEFAULT_REPLACEMENT}"
        assert result.output == "mail a@b.co"

    @pytest.mark.asyncio
    async def test_tool_guard_rejects_a_replace_verdict(self) -> None:
        """Test that redacting a tool result is rejected by the tool hook."""
        capability = _email_guard(type=["tool"])

        with pytest.raises(UserError, match="cannot return replace on tool"):
            await capability.after_tool_execute(
                run_context(),
                call=ToolCallPart("lookup", {"q": "x"}),
                tool_def=ToolDefinition(name="lookup"),
                args={"q": "x"},
                result="mail a@b.co",
            )

    @pytest.mark.asyncio
    async def test_tool_guard_returns_a_clean_result(self) -> None:
        """Test that a tool result with no match is returned unchanged."""
        capability = _email_guard(type=["tool"])

        result = await capability.after_tool_execute(
            run_context(),
            call=ToolCallPart("lookup", {"q": "x"}),
            tool_def=ToolDefinition(name="lookup"),
            args={"q": "x"},
            result="clean",
        )

        assert result == "clean"

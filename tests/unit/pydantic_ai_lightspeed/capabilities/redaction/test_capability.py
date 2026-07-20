"""Unit tests for pydantic_ai_lightspeed.capabilities.redaction.capability module."""

import re

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextContent,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestContext
from pytest_mock import MockerFixture

from models.config import (
    RedactionConfig,
    RedactionRule,
)
from pydantic_ai_lightspeed.capabilities.redaction._capability import (
    PiiRedactionCapability,
    _redact_content_item,
    _redact_content_list,
    _redact_message_parts,
    _redact_messages,
    _redact_model_request,
    _redact_response,
    _redact_user_prompt_part,
)
from pydantic_ai_lightspeed.capabilities.redaction.core import (
    CompiledPatterns,
)

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
EMAIL_PATTERNS: CompiledPatterns = [(EMAIL_PATTERN, "[REDACTED_EMAIL]")]


class TestRedactContentItem:
    """Tests for _redact_content_item helper."""

    def test_text_content_redacted(self) -> None:
        """Test redaction of a TextContent item."""
        tc = TextContent(content="email: user@test.com")
        result, changed = _redact_content_item(tc, EMAIL_PATTERNS)
        assert changed is True
        assert isinstance(result, TextContent)
        assert result.content == "email: [REDACTED_EMAIL]"

    def test_text_content_no_match(self) -> None:
        """Test that non-matching TextContent is returned unchanged."""
        tc = TextContent(content="safe text")
        result, changed = _redact_content_item(tc, EMAIL_PATTERNS)
        assert changed is False
        assert result is tc

    def test_string_content_redacted(self) -> None:
        """Test redaction of a plain string item."""
        result, changed = _redact_content_item("user@test.com", EMAIL_PATTERNS)
        assert changed is True
        assert result == "[REDACTED_EMAIL]"

    def test_string_content_no_match(self) -> None:
        """Test that non-matching string is returned unchanged."""
        result, changed = _redact_content_item("safe text", EMAIL_PATTERNS)
        assert changed is False
        assert result == "safe text"

    def test_other_type_passes_through(self) -> None:
        """Test that non-text types are returned unchanged."""
        sentinel = object()
        result, changed = _redact_content_item(sentinel, EMAIL_PATTERNS)
        assert changed is False
        assert result is sentinel


class TestRedactContentList:
    """Tests for _redact_content_list helper."""

    def test_redacts_matching_items(self) -> None:
        """Test that matching items in a list are redacted."""
        items = [TextContent(content="a@b.com"), "safe"]
        result = _redact_content_list(items, EMAIL_PATTERNS)
        assert result is not None
        assert result[0].content == "[REDACTED_EMAIL]"
        assert result[1] == "safe"

    def test_returns_none_when_no_match(self) -> None:
        """Test that None is returned when nothing changes."""
        items = [TextContent(content="safe"), "also safe"]
        result = _redact_content_list(items, EMAIL_PATTERNS)
        assert result is None

    def test_empty_list(self) -> None:
        """Test that an empty list returns None."""
        result = _redact_content_list([], EMAIL_PATTERNS)
        assert result is None


class TestRedactUserPromptPart:
    """Tests for _redact_user_prompt_part helper."""

    def test_string_content_redacted(self) -> None:
        """Test redaction of plain string content."""
        part = UserPromptPart(content="email: user@test.com")
        result = _redact_user_prompt_part(part, EMAIL_PATTERNS)
        assert result is not part
        assert result.content == "email: [REDACTED_EMAIL]"

    def test_string_content_no_match(self) -> None:
        """Test that non-matching string content returns the same instance."""
        part = UserPromptPart(content="no emails here")
        result = _redact_user_prompt_part(part, EMAIL_PATTERNS)
        assert result is part
        assert result.content == "no emails here"

    def test_text_content_sequence_redacted(self) -> None:
        """Test redaction of TextContent items in a sequence."""
        tc = TextContent(content="contact admin@corp.com")
        part = UserPromptPart(content=[tc])
        result = _redact_user_prompt_part(part, EMAIL_PATTERNS)
        assert result is not part
        assert result.content[0].content == "contact [REDACTED_EMAIL]"

    def test_text_content_sequence_no_match(self) -> None:
        """Test that non-matching TextContent sequence returns same instance."""
        tc = TextContent(content="safe text")
        part = UserPromptPart(content=[tc])
        result = _redact_user_prompt_part(part, EMAIL_PATTERNS)
        assert result is part


class TestRedactMessageParts:
    """Tests for _redact_message_parts helper."""

    def test_redacts_user_prompt_parts(self) -> None:
        """Test that UserPromptPart items are redacted."""
        parts = [UserPromptPart(content="a@b.com")]
        result = _redact_message_parts(parts, EMAIL_PATTERNS)
        assert result is not None
        assert result[0].content == "[REDACTED_EMAIL]"

    def test_returns_none_when_no_match(self) -> None:
        """Test that None is returned when nothing changes."""
        parts = [UserPromptPart(content="safe")]
        result = _redact_message_parts(parts, EMAIL_PATTERNS)
        assert result is None


class TestRedactModelRequest:
    """Tests for _redact_model_request helper."""

    def test_returns_new_request_when_redacted(self) -> None:
        """Test that a new ModelRequest is returned when parts change."""
        req = ModelRequest(parts=[UserPromptPart(content="a@b.com")])
        result = _redact_model_request(req, EMAIL_PATTERNS)
        assert result is not None
        assert result is not req
        assert result.parts[0].content == "[REDACTED_EMAIL]"

    def test_returns_none_when_no_match(self) -> None:
        """Test that None is returned when nothing changes."""
        req = ModelRequest(parts=[UserPromptPart(content="safe")])
        result = _redact_model_request(req, EMAIL_PATTERNS)
        assert result is None


class TestRedactMessages:
    """Tests for _redact_messages helper."""

    def test_redacts_user_prompt_in_request(self) -> None:
        """Test that user prompt parts within ModelRequest are redacted."""
        req = ModelRequest(parts=[UserPromptPart(content="hi user@x.com")])
        messages = [req]
        result = _redact_messages(messages, EMAIL_PATTERNS)
        assert result is not messages
        assert result[0].parts[0].content == "hi [REDACTED_EMAIL]"

    def test_skips_model_response_messages(self) -> None:
        """Test that ModelResponse messages pass through unchanged."""
        resp = ModelResponse(parts=[TextPart(content="user@x.com")])
        messages = [resp]
        result = _redact_messages(messages, EMAIL_PATTERNS)
        assert result is messages
        part = result[0].parts[0]
        assert isinstance(part, TextPart)
        assert part.content == "user@x.com"

    def test_no_redaction_returns_original_list(self) -> None:
        """Test that original list is returned when nothing changes."""
        req = ModelRequest(parts=[UserPromptPart(content="clean text")])
        messages = [req]
        result = _redact_messages(messages, EMAIL_PATTERNS)
        assert result is messages


class TestRedactResponse:
    """Tests for _redact_response helper."""

    def test_redacts_text_parts(self) -> None:
        """Test that text parts in a response are redacted."""
        resp = ModelResponse(parts=[TextPart(content="reply to user@x.com")])
        result = _redact_response(resp, EMAIL_PATTERNS)
        assert result is not resp
        part = result.parts[0]
        assert isinstance(part, TextPart)
        assert part.content == "reply to [REDACTED_EMAIL]"

    def test_no_match_returns_original(self) -> None:
        """Test that original response is returned when nothing matches."""
        resp = ModelResponse(parts=[TextPart(content="clean reply")])
        result = _redact_response(resp, EMAIL_PATTERNS)
        assert result is resp


class TestPiiRedactionCapability:
    """Tests for PiiRedactionCapability lifecycle hooks."""

    @pytest.fixture(name="capability")
    def capability_fixture(self) -> PiiRedactionCapability:
        """Create a PiiRedactionCapability with an email redaction rule.

        Returns:
            A configured PiiRedactionCapability instance.
        """
        config = RedactionConfig(
            rules=[
                RedactionRule(
                    pattern=r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                    replacement="[REDACTED_EMAIL]",
                )
            ],
            case_sensitive=True,
        )
        return PiiRedactionCapability(config=config)

    @pytest.mark.asyncio()
    async def test_before_model_request_redacts_user_messages(
        self,
        capability: PiiRedactionCapability,
        mocker: MockerFixture,
    ) -> None:
        """Test that before_model_request redacts PII from user messages."""
        req = ModelRequest(parts=[UserPromptPart(content="email: a@b.com")])
        request_context = ModelRequestContext(
            model=mocker.Mock(),
            messages=[req],
            model_settings=None,
            model_request_parameters=mocker.Mock(),
        )
        result = await capability.before_model_request(mocker.Mock(), request_context)
        assert result is not request_context
        assert result.messages[0].parts[0].content == "email: [REDACTED_EMAIL]"

    @pytest.mark.asyncio()
    async def test_before_model_request_no_match(
        self,
        capability: PiiRedactionCapability,
        mocker: MockerFixture,
    ) -> None:
        """Test that before_model_request returns original when nothing matches."""
        req = ModelRequest(parts=[UserPromptPart(content="safe text")])
        request_context = ModelRequestContext(
            model=mocker.Mock(),
            messages=[req],
            model_settings=None,
            model_request_parameters=mocker.Mock(),
        )
        result = await capability.before_model_request(mocker.Mock(), request_context)
        assert result is request_context
        assert req.parts[0].content == "safe text"

    @pytest.mark.asyncio()
    async def test_after_model_request_redacts_response(
        self,
        capability: PiiRedactionCapability,
        mocker: MockerFixture,
    ) -> None:
        """Test that after_model_request redacts PII from response text."""
        resp = ModelResponse(parts=[TextPart(content="leaked a@b.com")])
        request_context = ModelRequestContext(
            model=mocker.Mock(),
            messages=[],
            model_settings=None,
            model_request_parameters=mocker.Mock(),
        )
        result = await capability.after_model_request(
            mocker.Mock(),
            request_context=request_context,
            response=resp,
        )
        assert result is not resp
        part = result.parts[0]
        assert isinstance(part, TextPart)
        assert part.content == "leaked [REDACTED_EMAIL]"

    @pytest.mark.asyncio()
    async def test_after_model_request_no_match(
        self,
        capability: PiiRedactionCapability,
        mocker: MockerFixture,
    ) -> None:
        """Test that after_model_request returns original when nothing matches."""
        resp = ModelResponse(parts=[TextPart(content="clean response")])
        request_context = ModelRequestContext(
            model=mocker.Mock(),
            messages=[],
            model_settings=None,
            model_request_parameters=mocker.Mock(),
        )
        result = await capability.after_model_request(
            mocker.Mock(),
            request_context=request_context,
            response=resp,
        )
        assert result is resp
        assert resp.parts[0].content == "clean response"

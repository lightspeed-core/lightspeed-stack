"""Pydantic AI capability for PII redaction of model messages."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, Optional
from uuid import uuid4

from pydantic_ai import RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelRequestPart,
    ModelResponse,
    ModelResponsePart,
    TextContent,
    TextPart,
    UserContent,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestContext

from models.common.moderation import (
    ShieldModerationBlocked,
    ShieldModerationPassed,
    ShieldModerationResult,
)
from models.config import RedactionConfig
from pydantic_ai_lightspeed.capabilities.base import AbstractSafetyCapability
from pydantic_ai_lightspeed.capabilities.redaction.core import (
    CompiledPatterns,
    redact_text,
)


def _redact_string_content(
    text: str, compiled_patterns: CompiledPatterns
) -> Optional[str]:
    """Redact PII from a string and return the redacted version if changed.

    Args:
        text: The string to redact.
        compiled_patterns: Pre-compiled (pattern, replacement) pairs.

    Returns:
        The redacted string if redaction occurred, None otherwise.
    """
    result = redact_text(text, compiled_patterns)
    if result.redacted:
        return result.content
    return None


def _redact_text_content(
    item: TextContent, compiled_patterns: CompiledPatterns
) -> Optional[TextContent]:
    """Redact PII from TextContent and return a new instance if changed.

    Args:
        item: The TextContent to redact.
        compiled_patterns: Pre-compiled (pattern, replacement) pairs.

    Returns:
        A new TextContent with redacted content if changed, None otherwise.
    """
    redacted_text = _redact_string_content(item.content, compiled_patterns)
    if redacted_text is not None:
        return replace(item, content=redacted_text)
    return None


def _redact_content_item(
    item: UserContent, compiled_patterns: CompiledPatterns
) -> tuple[UserContent, bool]:
    """Redact a single content item and indicate whether it changed.

    Args:
        item: The content item to redact (TextContent, str, or other).
        compiled_patterns: Pre-compiled (pattern, replacement) pairs.

    Returns:
        A tuple of (redacted_item, changed_flag).
    """
    if isinstance(item, TextContent):
        redacted = _redact_text_content(item, compiled_patterns)
        if redacted is not None:
            return redacted, True
        return item, False

    if isinstance(item, str):
        redacted_text = _redact_string_content(item, compiled_patterns)
        if redacted_text is not None:
            return redacted_text, True
        return item, False

    return item, False


def _redact_content_list(
    content: Sequence[UserContent], compiled_patterns: CompiledPatterns
) -> Optional[list[UserContent]]:
    """Redact PII from a list of content items.

    Args:
        content: The list of content items to redact.
        compiled_patterns: Pre-compiled (pattern, replacement) pairs.

    Returns:
        A new list with redacted items if any changed, None otherwise.
    """
    new_items: list[UserContent] = []
    any_changed = False

    for item in content:
        redacted_item, changed = _redact_content_item(item, compiled_patterns)
        new_items.append(redacted_item)
        any_changed = any_changed or changed

    if any_changed:
        return new_items
    return None


def _redact_user_prompt_part(
    part: UserPromptPart,
    compiled_patterns: CompiledPatterns,
) -> UserPromptPart:
    """Return a new UserPromptPart with PII redacted from text content.

    Returns the original instance unchanged if no redaction occurred.
    Callers can detect changes via identity (``new is not original``).

    Args:
        part: The user prompt part to redact.
        compiled_patterns: Pre-compiled (pattern, replacement) pairs.

    Returns:
        A new UserPromptPart with redacted content, or the original.
    """
    if isinstance(part.content, str):
        redacted_text = _redact_string_content(part.content, compiled_patterns)
        if redacted_text is not None:
            return replace(part, content=redacted_text)
        return part

    redacted_list = _redact_content_list(part.content, compiled_patterns)
    if redacted_list is not None:
        return replace(part, content=redacted_list)
    return part


def _redact_message_parts(
    parts: Sequence[ModelRequestPart], compiled_patterns: CompiledPatterns
) -> Optional[list[ModelRequestPart]]:
    """Redact PII from message parts.

    Args:
        parts: The message parts to redact.
        compiled_patterns: Pre-compiled (pattern, replacement) pairs.

    Returns:
        A new list with redacted parts if any changed, None otherwise.
    """
    new_parts: list[ModelRequestPart] = []
    any_changed = False

    for part in parts:
        if isinstance(part, UserPromptPart):
            redacted_part = _redact_user_prompt_part(part, compiled_patterns)
            new_parts.append(redacted_part)
            any_changed = any_changed or (redacted_part is not part)
        else:
            new_parts.append(part)

    if any_changed:
        return new_parts
    return None


def _redact_model_request(
    message: ModelRequest, compiled_patterns: CompiledPatterns
) -> Optional[ModelRequest]:
    """Redact PII from a ModelRequest message.

    Args:
        message: The ModelRequest to redact.
        compiled_patterns: Pre-compiled (pattern, replacement) pairs.

    Returns:
        A new ModelRequest with redacted parts if changed, None otherwise.
    """
    redacted_parts = _redact_message_parts(message.parts, compiled_patterns)
    if redacted_parts is not None:
        return replace(message, parts=redacted_parts)
    return None


def _redact_messages(
    messages: list[ModelMessage],
    compiled_patterns: CompiledPatterns,
) -> list[ModelMessage]:
    """Return a new message list with PII redacted from user prompt parts.

    Returns the original list unchanged if no redaction occurred.

    Args:
        messages: The messages to scan and redact.
        compiled_patterns: Pre-compiled (pattern, replacement) pairs.

    Returns:
        A new list with redacted messages, or the original list.
    """
    new_messages: list[ModelMessage] = []
    any_changed = False

    for message in messages:
        if isinstance(message, ModelRequest):
            redacted_message = _redact_model_request(message, compiled_patterns)
            if redacted_message is not None:
                new_messages.append(redacted_message)
                any_changed = True
            else:
                new_messages.append(message)
        else:
            new_messages.append(message)

    if any_changed:
        return new_messages
    return messages


def _redact_response(
    response: ModelResponse,
    compiled_patterns: CompiledPatterns,
) -> ModelResponse:
    """Return a new ModelResponse with PII redacted from text parts.

    Returns the original instance unchanged if no redaction occurred.

    Args:
        response: The model response to scan and redact.
        compiled_patterns: Pre-compiled (pattern, replacement) pairs.

    Returns:
        A new ModelResponse with redacted content, or the original.
    """
    changed = False
    new_parts: list[ModelResponsePart] = []

    for part in response.parts:
        if isinstance(part, TextPart):
            result = redact_text(part.content, compiled_patterns)
            if result.redacted:
                new_parts.append(replace(part, content=result.content))
                changed = True
            else:
                new_parts.append(part)
        else:
            new_parts.append(part)

    if changed:
        return replace(response, parts=new_parts)
    return response


@dataclass
class PiiRedactionCapability(AbstractSafetyCapability):
    """Pydantic AI capability that redacts PII from agent messages.

    Applies configurable regex-based redaction rules to user prompt
    text before it reaches the model, and to model response text
    before it is returned to the caller.

    Rules are validated and compiled at configuration time via
    ``RedactionConfig``. Invalid regex patterns are rejected
    immediately with a clear error.

    Attributes:
        config: Redaction configuration with compiled regex rules.
    """

    config: RedactionConfig

    async def before_model_request(
        self,
        ctx: RunContext[Any],
        request_context: ModelRequestContext,
    ) -> ModelRequestContext:
        """Redact PII from user messages before they reach the model.

        Args:
            ctx: The current run context.
            request_context: The model request context containing messages.

        Returns:
            A new ModelRequestContext with redacted messages, or the
            original if no redaction occurred.
        """
        new_messages = _redact_messages(
            request_context.messages,
            self.config.compiled_patterns,
        )
        if new_messages is not request_context.messages:
            return replace(request_context, messages=new_messages)
        return request_context

    async def after_model_request(
        self,
        ctx: RunContext[Any],
        *,
        request_context: ModelRequestContext,
        response: ModelResponse,
    ) -> ModelResponse:
        """Redact PII from model response text parts.

        Args:
            ctx: The current run context.
            request_context: The model request context.
            response: The model response to redact.

        Returns:
            A new ModelResponse with redacted text parts, or the
            original if no redaction occurred.
        """
        new_response = _redact_response(
            response,
            self.config.compiled_patterns,
        )

        return new_response

    async def run(self, input_text: str) -> ShieldModerationResult:
        result = redact_text(input_text, self.config.compiled_patterns)

        if result.redacted:
            return ShieldModerationBlocked(
                message="Sensitive content detected.", moderation_id=f"modr-{uuid4()}"
            )

        return ShieldModerationPassed()

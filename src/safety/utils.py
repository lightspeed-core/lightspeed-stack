"""Shared helpers for reading and editing the current model request's messages.

Factored out of :mod:`lightspeed.core.agent.safety.base` so capabilities that
need to inspect or adjust the latest user-facing prompt -- safety input
guards, the ``Knowledge`` capability's inline injection -- don't each
reimplement the same message-history scan. Also renders tool results so
``'tool'`` guards can call ``evaluate`` on them.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Optional

from pydantic import BaseModel
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolReturn,
    UserContent,
    UserPromptPart,
)


def find_latest_part[PartT](
    messages: Sequence[ModelMessage], part_type: type[PartT]
) -> Optional[PartT]:
    """Return the most recent part of `part_type` in `messages`, scanning newest-first.

    Shared by `extract_prompt_text` (reads it) and `replace_latest_message`
    (rewrites it) so both agree on what "the current user prompt" means, and
    reusable for any other part type a future capability needs to locate the
    same way (e.g. the last `ToolReturnPart`).
    """
    for message in reversed(messages):
        for part in reversed(message.parts):
            if isinstance(part, part_type):
                return part
    return None


def find_latest_message[MessageT](
    messages: Sequence[ModelMessage], message_type: type[MessageT]
) -> Optional[MessageT]:
    """Return the most recent message of `message_type` in `messages`, scanning newest-first.

    The message-level counterpart to `find_latest_part`: useful when a
    capability needs the message itself -- e.g. the last `ModelResponse` --
    rather than a part nested inside one.
    """
    for message in reversed(messages):
        if isinstance(message, message_type):
            return message
    return None


def extract_latest_message_text(messages: Sequence[ModelMessage]) -> str | None:
    """Return the text of the most recent user prompt, or `None` if absent.

    Scans the message history for the last [`UserPromptPart`][pydantic_ai.messages.UserPromptPart].
    """
    part = find_latest_part(messages, UserPromptPart)
    if not isinstance(part, UserPromptPart):
        return None
    return part.content if isinstance(part.content, str) else str(part.content)


def append_latest_message(
    messages: Sequence[ModelMessage], content: str | Sequence[UserContent]
) -> None:
    """Append a new user prompt with `content` to the latest message, mutating it in place.

    Takes the same `content` type as `replace_latest_message` -- the two
    are meant to be used identically, one adding a part and the other
    rewriting the latest one. `ModelRequest` isn't frozen, so this just
    reassigns its `parts` field -- no need to rebuild the message or write
    back into `messages`.

    Raises:
        RuntimeError: If no `ModelRequest` is found in `messages`. The agent
            graph only calls request hooks when message history ends with
            one, so this should never trigger in practice.

    """
    latest = find_latest_message(messages, ModelRequest)
    if latest is None:  # pragma: no cover - guaranteed by the agent graph
        raise RuntimeError("model request history must include a ModelRequest")
    latest.parts = [*latest.parts, UserPromptPart(content)]


def replace_latest_message(
    messages: Sequence[ModelMessage], content: str | Sequence[UserContent]
) -> bool:
    """Rewrite the most recent user prompt to `content`, mutating it in place.

    Takes the same `content` type as `append_latest_message` -- the two
    are meant to be used identically, one rewriting the latest user prompt
    and the other adding a new one. Returns whether a user prompt was found
    to rewrite.

    Refuses to overwrite a multimodal prompt with plain text: the existing
    `content` is a sequence of parts, and a bare `str` written over it would
    send the model the replacement text alone -- the images, documents, and
    audio the user attached would be gone, with nothing in the run to say so.
    Pass a `Sequence[UserContent]` instead to replace multimodal content with
    different multimodal content.
    """
    part = find_latest_part(messages, UserPromptPart)
    if part is None:
        return False
    if isinstance(content, str) and not isinstance(part.content, str):
        raise UserError(
            f"Cannot replace a multimodal user prompt with plain text. The prompt holds "
            f"{type(part.content).__name__} rather than text, so writing the replacement "
            "over it would drop the attached parts. Pass a Sequence[UserContent] instead "
            "to replace it with multimodal content."
        )
    part.content = content
    return True


def tool_result_to_str(result: Any) -> str:
    """Render a raw tool execution result as text for `evaluate`.

    `result` is whatever the tool function itself returned (str, dict, Pydantic
    model, `ToolReturn`, etc.), captured before pydantic-ai serializes it into the
    `ToolReturnPart` sent back to the model. This best-effort conversion mirrors
    that later serialization closely enough for risk screening without depending
    on pydantic-ai's internals.
    """
    if isinstance(result, str):
        return result

    if isinstance(result, ToolReturn):
        return tool_result_to_str(result.return_value)

    if isinstance(result, BaseModel):
        return result.model_dump_json()

    try:
        return json.dumps(result, default=str)
    except TypeError:
        return str(result)

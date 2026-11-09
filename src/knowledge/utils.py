"""Shared helpers for reading and editing the current model request's messages.

Factored out of :mod:`lightspeed.core.agent.safety.base` so capabilities that
need to inspect or adjust the latest user-facing prompt -- safety input
guards, the ``Knowledge`` capability's inline injection -- don't each
reimplement the same message-history scan.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Optional, TypeVar

from pydantic_ai.messages import ModelMessage, ModelRequest, UserContent, UserPromptPart

PartT = TypeVar("PartT")
MessageT = TypeVar("MessageT")


def find_latest_part(
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


def find_latest_message(
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


def extract_latest_message_text(messages: Sequence[ModelMessage]) -> Optional[str]:
    """Return the text of the most recent user prompt, or `None` if absent.

    Scans the message history for the last [`UserPromptPart`][pydantic_ai.messages.UserPromptPart].
    """
    part = find_latest_part(messages, UserPromptPart)
    if not isinstance(part, UserPromptPart):
        return None
    return part.content if isinstance(part.content, str) else str(part.content)


def append_latest_message(
    messages: Sequence[ModelMessage], content: UserContent | Sequence[UserContent]
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

    if not isinstance(content, (str, Sequence)):
        content = [content]

    latest.parts = [*latest.parts, UserPromptPart(content)]

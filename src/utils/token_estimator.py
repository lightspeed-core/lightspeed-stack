"""Pre-LLM-call token estimation.

This module estimates the number of tokens a prompt will consume *before*
the request is sent to the LLM. The conversation compaction trigger uses
the estimate to decide when older conversation turns must be summarized
to keep the request inside the model's context window.

Estimation is performed with the ``tiktoken`` library against an
OpenAI-compatible encoding (``cl100k_base`` by default — the family used
by GPT-3.5, GPT-4, and GPT-4o). Encodings are cached at module level so
the wheel-bundled BPE tables are only loaded once per process.

The function ``estimate_conversation_tokens`` understands two shapes of
chat-message: Llama Stack conversation-item objects (with ``.type``,
``.role``, ``.content`` attributes) and plain ``{"role", "content"}``
dictionaries. The duck-typed shape lets the caller pass whatever the
local code path produces without an adapter.
"""

from functools import lru_cache
from typing import Any, Optional

import tiktoken

from log import get_logger
from models.config import InferenceConfiguration

logger = get_logger(__name__)

DEFAULT_ENCODING_NAME = "cl100k_base"
"""Default tiktoken encoding name used when the caller does not pick one."""


@lru_cache(maxsize=8)
def _get_encoding(encoding_name: str) -> tiktoken.Encoding:
    """Return a cached tiktoken Encoding for *encoding_name*.

    The result is memoized so the BPE merge tables are loaded once per
    encoding per process. ``maxsize=8`` covers every encoding tiktoken
    ships with comfortable headroom.

    Parameters:
        encoding_name: Name accepted by ``tiktoken.get_encoding`` (e.g.,
            ``"cl100k_base"``, ``"o200k_base"``).

    Returns:
        The encoding object.

    Raises:
        ValueError: Propagated from tiktoken when the encoding name is
            unknown.
    """
    return tiktoken.get_encoding(encoding_name)


def estimate_tokens(text: str, encoding_name: str = DEFAULT_ENCODING_NAME) -> int:
    """Estimate the number of tokens *text* will consume.

    Tokenization is performed with ``tiktoken`` against *encoding_name*.
    The function returns 0 for the empty string and a positive integer
    for any non-empty text containing recognizable characters.

    Parameters:
        text: Text whose token count should be estimated.
        encoding_name: Name of the tiktoken encoding to use. Defaults to
            ``"cl100k_base"`` (the GPT-3.5 / GPT-4 / GPT-4o family).

    Returns:
        The token count.

    Raises:
        ValueError: When *encoding_name* is not recognized by tiktoken.
    """
    if not text:
        return 0
    return len(_get_encoding(encoding_name).encode(text))


def extract_message_text(message: Any) -> str:
    """Pull the textual content out of a chat-message-shaped value.

    Accepts the duck-typed Llama Stack conversation-item shape
    (``.type == "message"`` with ``.role`` and ``.content`` attributes)
    and the OpenAI-style ``{"role", "content"}`` dictionary.

    ``content`` can be a plain string, a list of content-part objects
    each with a ``.text`` attribute, or a list of dicts each with a
    ``"text"`` key. Anything unrecognized is coerced via ``str(...)``.

    Parameters:
        message: Chat-message-shaped value.

    Returns:
        The textual content joined by spaces, or the empty string when
        no text can be located.
    """
    content: Any
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)

    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if hasattr(part, "text"):
                text = getattr(part, "text", None)
                if text:
                    parts.append(text)
            elif isinstance(part, dict) and "text" in part:
                text = part["text"]
                if text:
                    parts.append(text)
        return " ".join(parts)
    return str(content)


def is_message_item(value: Any) -> bool:
    """Return True when *value* looks like a chat message.

    Either an OpenAI-style dict with a ``"role"`` key, or a Llama Stack
    conversation-item object whose ``.type`` attribute is ``"message"``.
    """
    if isinstance(value, dict):
        return "role" in value
    return getattr(value, "type", None) == "message"


def estimate_conversation_tokens(
    messages: list[Any],
    system_prompt: Optional[str] = None,
    encoding_name: str = DEFAULT_ENCODING_NAME,
) -> int:
    """Estimate the token count of a chat conversation.

    Sums tokens across the optional system prompt and every message in
    *messages*. Non-message items in the list (tool calls, function
    results, etc.) are ignored — only items recognized by
    ``is_message_item`` contribute. Both Llama Stack conversation-item
    objects and plain ``{"role", "content"}`` dicts are accepted in the
    same list.

    Parameters:
        messages: Chat history. Each element may be a Llama Stack
            conversation item or a plain dict.
        system_prompt: Optional system prompt prepended to the
            estimate.
        encoding_name: Name of the tiktoken encoding to use.

    Returns:
        The total token count.
    """
    encoding = _get_encoding(encoding_name)
    total = 0
    if system_prompt:
        total += len(encoding.encode(system_prompt))
    for message in messages:
        if not is_message_item(message):
            continue
        text = extract_message_text(message)
        if text:
            total += len(encoding.encode(text))
    return total


def get_context_window(
    model: str, inference_config: InferenceConfiguration
) -> Optional[int]:
    """Return the configured context window size for *model* in tokens.

    Looks up *model* in ``inference_config.context_windows``. Returns
    ``None`` when the model is absent from the map. The caller decides
    how to handle the absence — typically, skipping the token-based
    compaction trigger.

    Parameters:
        model: Fully-qualified model identifier (e.g.,
            ``"openai/gpt-4o-mini"``).
        inference_config: The application's inference configuration.

    Returns:
        The context window size in tokens, or ``None`` when unset.
    """
    return inference_config.context_windows.get(model)

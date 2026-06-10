"""Round-trip Gemini 3 thought signatures through llama-stack's Vertex AI path.

Gemini 3.x models (for example ``gemini-3-flash`` and ``gemini-3.5-flash``)
attach a ``thought_signature`` to the first ``functionCall`` part of a
tool-calling turn. The signature MUST be replayed verbatim on the following
turn or Gemini rejects the request with HTTP 400.

llama-stack converts Gemini responses into the OpenAI chat-completion shape
before they re-enter its own history, and that shape has no field for a
thought signature, so the signature is dropped and every multi-turn tool call
against a Gemini 3 model fails. This module monkeypatches llama-stack's
``vertexai`` converter so the signature survives the round trip.

Strategy: both patched functions are thin wrappers around the upstream
originals. We copy none of llama-stack's conversion logic; we only smuggle the
signature in and out through the opaque tool-call ``id`` (which llama-stack
round-trips untouched and only ever compares for equality).

- On the way out (Gemini -> OpenAI): ``_extract_candidate_parts`` produces a
  random tool-call id per ``functionCall`` part. We call the original, then
  re-walk the candidate's parts in the same deterministic order, pair each
  ``functionCall`` part with the tool call the original emitted, and rewrite
  that tool call's id to embed the base64-encoded signature.

- On the way back (OpenAI -> Gemini): ``_convert_assistant_message`` builds
  the Gemini ``parts``. We call the original, then re-pair each
  ``function_call`` part with its source tool call (same order) and attach the
  decoded signature.

This file shadows behaviour tied to a specific llama-stack release. Remove it
once the upstream Vertex AI provider carries thought signatures natively.
"""

# This module is a monkeypatch shim for llama-stack's Vertex AI converter. It
# necessarily reaches into the provider's protected (underscore-prefixed)
# converter functions, so protected-access is disabled file-wide here rather
# than annotated on every line.
# pylint: disable=protected-access
import base64
from typing import Any

from log import get_logger

logger = get_logger(__name__)

# Sentinel separating the real tool-call id from a smuggled Gemini
# thought_signature. Chosen to be vanishingly unlikely in a normal id.
_THOUGHT_SIG_SEP = "::gts::"

# Set once the patch has been applied so repeated startup calls are no-ops.
_PATCH_APPLIED = False


def _encode_thought_signature_into_id(call_id: str, signature: Any) -> str:
    """Append a base64-encoded Gemini thought_signature to a tool-call id.

    The signature is bytes; the id must stay a plain string that round-trips
    through llama-stack history. Returns ``call_id`` unchanged when there is no
    signature to carry or it cannot be encoded.
    """
    if not signature:
        return call_id
    try:
        raw = (
            signature.encode("utf-8")
            if isinstance(signature, str)
            else bytes(signature)
        )
        encoded = base64.b64encode(raw).decode("ascii")
    except (TypeError, ValueError):
        return call_id
    return f"{call_id}{_THOUGHT_SIG_SEP}{encoded}"


def _decode_thought_signature_from_id(call_id: str) -> bytes | None:
    """Recover the thought_signature bytes smuggled into a tool-call id."""
    if not call_id or _THOUGHT_SIG_SEP not in call_id:
        return None
    _, _, encoded = call_id.partition(_THOUGHT_SIG_SEP)
    try:
        return base64.b64decode(encoded)
    except (ValueError, TypeError):
        return None


def _tag_wrapper(wrapper: Any, original: Any) -> None:
    """Mark ``wrapper`` as an LCS converter patch wrapping ``original``.

    The markers make the patched state self-describing: ``apply_patch`` reads
    ``__wrapped_by_lcs__`` to avoid double-wrapping, and callers can follow
    ``__lcs_original__`` back to the pristine converter.
    """
    wrapper.__wrapped_by_lcs__ = True
    wrapper.__lcs_original__ = original


def _is_lcs_wrapped(func: Any) -> bool:
    """Return whether ``func`` is an LCS converter patch wrapper."""
    return bool(getattr(func, "__wrapped_by_lcs__", False))


def _unwrap_to_original(func: Any) -> Any:
    """Follow ``__lcs_original__`` links until the pristine converter is found."""
    while _is_lcs_wrapped(func):
        func = func.__lcs_original__
    return func


def _iter_function_call_parts(candidate: Any) -> list[Any]:
    """Return the ``functionCall`` parts of a Gemini candidate, in order.

    Mirrors the iteration order llama-stack's ``_extract_candidate_parts`` uses
    so the parts line up one-to-one with the tool calls it produces.
    """
    content_obj = getattr(candidate, "content", None)
    parts = getattr(content_obj, "parts", None) or []
    fc_parts: list[Any] = []
    for part in parts:
        # Thinking parts and text parts are skipped before the function-call
        # branch upstream; replicate that ordering precisely.
        if getattr(part, "thought", None):
            continue
        if getattr(part, "text", None) is not None:
            continue
        if getattr(part, "function_call", None) is not None:
            fc_parts.append(part)
    return fc_parts


def apply_patch() -> bool:
    """Monkeypatch the Vertex AI converter to carry Gemini thought signatures.

    Idempotent. Returns ``True`` if the patch is in effect after the call,
    ``False`` if the converter module could not be imported (for example when
    the Vertex AI provider is not installed), in which case nothing is changed.
    """
    global _PATCH_APPLIED  # pylint: disable=global-statement
    if _PATCH_APPLIED:
        return True

    try:
        # Imported lazily: the provider is optional, so a top-level import
        # would break environments where the Vertex AI provider is absent.
        from llama_stack.providers.remote.inference.vertexai import (  # pylint: disable=import-outside-toplevel
            converters,
        )
    except ImportError:
        logger.info(
            "Vertex AI converter not importable; skipping Gemini thought-signature patch"
        )
        return False

    # Guard against re-wrapping an already-wrapped converter. The module-level
    # flag is the fast path, but a second importer (or a test that clears the
    # flag) must not double-wrap: that would encode the signature twice. The
    # marker attribute makes the wrapped state detectable on the function
    # itself, independent of the flag.
    if _is_lcs_wrapped(converters._extract_candidate_parts):
        _PATCH_APPLIED = True
        return True

    original_extract = converters._extract_candidate_parts
    original_convert_assistant = converters._convert_assistant_message

    def patched_extract_candidate_parts(candidate: Any) -> Any:
        text_parts, thinking_parts, tool_calls = original_extract(candidate)
        if not tool_calls:
            return text_parts, thinking_parts, tool_calls
        fc_parts = _iter_function_call_parts(candidate)
        # The original emits exactly one tool call per function-call part, in
        # the same order. Pair them and embed any signature into the id.
        for tool_call, part in zip(tool_calls, fc_parts):
            signature = getattr(part, "thought_signature", None)
            if not signature:
                continue
            tool_call.id = _encode_thought_signature_into_id(
                tool_call.id or "", signature
            )
        return text_parts, thinking_parts, tool_calls

    def patched_convert_assistant_message(msg: dict[str, Any]) -> dict[str, Any] | None:
        result = original_convert_assistant(msg)
        if result is None:
            return None
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return result
        # Re-pair each Gemini function_call part with its source tool call, in
        # order, and attach the decoded signature. The original appends one
        # function_call part per tool call after any leading text part, so we
        # walk the function_call parts and the tool calls together.
        fc_parts = [p for p in result.get("parts", []) if "function_call" in p]
        for part, tool_call in zip(fc_parts, tool_calls):
            call_id = converters._to_dict(tool_call).get("id", "")
            signature = _decode_thought_signature_from_id(call_id)
            if signature is not None:
                part["thought_signature"] = signature
        return result

    # Tag each wrapper so it is self-describing: ``__wrapped_by_lcs__`` lets a
    # second apply_patch detect the patched state, and ``__lcs_original__``
    # lets callers (notably tests) unwind back to the pristine original.
    _tag_wrapper(patched_extract_candidate_parts, original_extract)
    _tag_wrapper(patched_convert_assistant_message, original_convert_assistant)

    converters._extract_candidate_parts = patched_extract_candidate_parts
    converters._convert_assistant_message = patched_convert_assistant_message
    _PATCH_APPLIED = True
    logger.info("Applied Gemini 3 thought-signature patch to Vertex AI converter")
    return True

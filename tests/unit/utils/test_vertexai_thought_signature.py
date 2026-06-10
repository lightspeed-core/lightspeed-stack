"""Unit tests for the Gemini 3 thought-signature Vertex AI converter patch."""

# The patch under test is a monkeypatch shim that reaches into the converter's
# protected helpers, and the small local factory helpers below need no
# docstrings. Disable both checks file-wide for this test module.
# pylint: disable=protected-access,missing-function-docstring

import builtins
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from pytest import MonkeyPatch

from utils import vertexai_thought_signature as patch


@pytest.fixture(autouse=True)
def _reset_patch_state(monkeypatch: MonkeyPatch) -> Iterator[None]:
    """Each test starts from a pristine, unpatched converter.

    ``app.main`` applies the patch at import time, so by the time this test
    module runs the converter may already be wrapped and ``_PATCH_APPLIED`` may
    be ``True``. Naively clearing the flag would let ``apply_patch`` re-wrap an
    already-wrapped function and double-encode the signature. Instead, snapshot
    the real converter functions, run the test against pristine originals, and
    restore the snapshot afterwards.
    """
    monkeypatch.setattr(patch, "_PATCH_APPLIED", False)
    converters = pytest.importorskip(
        "llama_stack.providers.remote.inference.vertexai.converters"
    )

    saved_extract = converters._extract_candidate_parts
    saved_convert = converters._convert_assistant_message
    # Unwind any patch app.main left in place so each test starts pristine.
    converters._extract_candidate_parts = patch._unwrap_to_original(saved_extract)
    converters._convert_assistant_message = patch._unwrap_to_original(saved_convert)
    try:
        yield
    finally:
        converters._extract_candidate_parts = saved_extract
        converters._convert_assistant_message = saved_convert


class TestEncodeDecode:
    """The base64 smuggling helpers round-trip signatures through the id."""

    def test_round_trip_bytes(self) -> None:
        sig = b"\x01\x02\xfe\xffsig"
        encoded = patch._encode_thought_signature_into_id("call_x", sig)
        assert encoded.startswith("call_x")
        assert patch._THOUGHT_SIG_SEP in encoded
        assert patch._decode_thought_signature_from_id(encoded) == sig

    def test_round_trip_str_signature(self) -> None:
        encoded = patch._encode_thought_signature_into_id("call_x", "abc")
        assert patch._decode_thought_signature_from_id(encoded) == b"abc"

    def test_no_signature_leaves_id_untouched(self) -> None:
        assert patch._encode_thought_signature_into_id("call_x", None) == "call_x"
        assert patch._encode_thought_signature_into_id("call_x", b"") == "call_x"

    def test_plain_id_decodes_to_none(self) -> None:
        assert patch._decode_thought_signature_from_id("call_x") is None
        assert patch._decode_thought_signature_from_id("") is None

    def test_corrupt_payload_decodes_to_none(self) -> None:
        corrupt = f"call_x{patch._THOUGHT_SIG_SEP}!!!not-base64!!!"
        assert patch._decode_thought_signature_from_id(corrupt) is None


def _make_part(**kw: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "thought": None,
        "text": None,
        "function_call": None,
        "thought_signature": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _make_candidate(parts: list[Any]) -> SimpleNamespace:
    return SimpleNamespace(content=SimpleNamespace(parts=parts), finish_reason=None)


class TestApplyPatch:
    """apply_patch wires the wrappers onto the real converter and is idempotent."""

    def test_apply_is_idempotent(self) -> None:
        converters = pytest.importorskip(
            "llama_stack.providers.remote.inference.vertexai.converters"
        )
        assert patch.apply_patch() is True
        first = converters._extract_candidate_parts
        assert patch.apply_patch() is True
        assert converters._extract_candidate_parts is first

    def test_apply_missing_provider_returns_false(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        real_import = builtins.__import__

        def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name.startswith("llama_stack.providers.remote.inference.vertexai"):
                raise ImportError("provider not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert patch.apply_patch() is False

    def test_extract_embeds_signature_into_tool_call_id(self) -> None:
        converters = pytest.importorskip(
            "llama_stack.providers.remote.inference.vertexai.converters"
        )
        patch.apply_patch()
        sig = b"\x10\x20signature"
        fc = SimpleNamespace(name="search_portal", args={"q": "selinux"})
        cand = _make_candidate(
            [
                _make_part(text="thinking"),
                _make_part(function_call=fc, thought_signature=sig),
            ]
        )
        _text, _thinking, tool_calls = converters._extract_candidate_parts(cand)
        assert len(tool_calls) == 1
        # name stays clean, signature rides on the id
        assert tool_calls[0].function.name == "search_portal"
        assert patch._decode_thought_signature_from_id(tool_calls[0].id) == sig

    def test_round_trip_through_assistant_message(self) -> None:
        converters = pytest.importorskip(
            "llama_stack.providers.remote.inference.vertexai.converters"
        )
        patch.apply_patch()
        sig = b"round-trip-bytes"
        fc = SimpleNamespace(name="get_document", args={"id": "1"})
        cand = _make_candidate([_make_part(function_call=fc, thought_signature=sig)])
        _t, _th, tool_calls = converters._extract_candidate_parts(cand)

        msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_calls[0].id,
                    "type": "function",
                    "function": {"name": "get_document", "arguments": '{"id":"1"}'},
                }
            ],
        }
        out = converters._convert_assistant_message(msg)
        fc_parts = [p for p in out["parts"] if "function_call" in p]
        assert len(fc_parts) == 1
        assert fc_parts[0]["thought_signature"] == sig

    def test_tool_call_without_signature_stays_clean(self) -> None:
        converters = pytest.importorskip(
            "llama_stack.providers.remote.inference.vertexai.converters"
        )
        patch.apply_patch()
        msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_plain",
                    "type": "function",
                    "function": {"name": "x", "arguments": "{}"},
                }
            ],
        }
        out = converters._convert_assistant_message(msg)
        fc_part = next(p for p in out["parts"] if "function_call" in p)
        assert "thought_signature" not in fc_part

    def test_reapply_after_flag_reset_does_not_double_wrap(self) -> None:
        """Re-applying after the guard flag is cleared must not double-encode.

        ``app.main`` applies the patch at import time. If a later caller clears
        ``_PATCH_APPLIED`` and calls ``apply_patch`` again, the wrapper must not
        wrap an already-wrapped converter (which would base64-encode the
        signature twice and corrupt it). This reproduces the original CI break.
        """
        converters = pytest.importorskip(
            "llama_stack.providers.remote.inference.vertexai.converters"
        )
        patch.apply_patch()
        wrapped_once = converters._extract_candidate_parts

        # Simulate the flag being cleared out from under us (as a sibling test
        # module's autouse fixture would do) and re-applying.
        patch._PATCH_APPLIED = False
        assert patch.apply_patch() is True
        # The converter is the same single-wrapped function, not re-wrapped.
        assert converters._extract_candidate_parts is wrapped_once

        sig = b"\x10\x20signature"
        fc = SimpleNamespace(name="search_portal", args={"q": "selinux"})
        cand = _make_candidate([_make_part(function_call=fc, thought_signature=sig)])
        _t, _th, tool_calls = converters._extract_candidate_parts(cand)
        # Signature survives a single round-trip, not a doubled payload.
        assert patch._decode_thought_signature_from_id(tool_calls[0].id) == sig

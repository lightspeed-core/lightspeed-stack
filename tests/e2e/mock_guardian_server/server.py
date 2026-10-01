#!/usr/bin/env python3
"""Mock OpenAI-compatible Granite Guardian endpoint for E2E tests.

Implements ``/v1/chat/completions`` with the logprobs shape required by
``pydantic_ai_lightspeed.capabilities.granite_guardian``. Jailbreak-style
input, restricted-persona output, and poisoned tool text are scored risky;
everything else is scored safe.

Run as ``python server.py [port]``; default port is 8001.
"""

import json
import math
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

DEFAULT_PORT = 8001
_MAX_BODY_BYTES = 1 * 1024 * 1024  # reject chat-completion bodies larger than 1 MiB

# Keep these more specific than "you are now" so legitimate cluster-admin
# prompts are not blocked.
_RISKY_MARKERS = (
    "ignore all previous instructions",
    "you are now dan",
    "unrestricted persona",
    "disabled all safety filters",
    "ignore previous instructions",
    "unrestricted assistant",
)


def _scored_text_from_body(raw: bytes) -> str:
    """Return the user text being scored, excluding Guardian system instructions.

    Granite Guardian requests put criteria in a ``system`` message and the
    content under evaluation in a ``user`` message. Risk descriptions may
    quote jailbreak phrases, so scanning the raw body would false-positive.
    """
    try:
        payload = json.loads(raw.decode("utf-8", "ignore") or "{}")
    except json.JSONDecodeError:
        return ""

    messages = payload.get("messages")
    if not isinstance(messages, list):
        return ""

    parts: list[str] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
    return "\n".join(parts)


def _score_logprobs(risky: bool) -> list[dict[str, Any]]:
    """Return logprobs for ``</think><score>{yes|no}</score>``.

    The granite_guardian parser needs four separate tokens and reads P(yes)
    from the score token's ``top_logprobs``.
    """
    yes_lp = math.log(0.9 if risky else 0.1)
    no_lp = math.log(0.1 if risky else 0.9)
    token = "yes" if risky else "no"
    top = [{"token": "no", "logprob": no_lp}, {"token": "yes", "logprob": yes_lp}]
    return [
        {"token": tag, "logprob": lp, "top_logprobs": tops}
        for tag, lp, tops in (
            ("</think>", 0.0, []),
            ("<score>", 0.0, []),
            (token, yes_lp if risky else no_lp, top),
            ("</score>", 0.0, []),
        )
    ]


class Handler(BaseHTTPRequestHandler):
    """HTTP handler for health and chat completions."""

    def log_message(self, format: str, *args: Any) -> None:
        """Keep mock output quiet during e2e runs."""

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        """Send a JSON response."""
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        """Handle the Compose health probe."""
        if self.path.split("?", 1)[0] == "/health":
            self._send_json({"status": "ok"})
            return
        self.send_error(404)

    def do_POST(self) -> None:
        """Handle chat-completions scoring requests."""
        if self.path.split("?", 1)[0] != "/v1/chat/completions":
            self.send_error(404)
            return

        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            self.send_error(400, "invalid content-length")
            return
        if length < 0 or length > _MAX_BODY_BYTES:
            self.send_error(413, "payload too large")
            return

        raw = self.rfile.read(length) if length else b""
        scored = _scored_text_from_body(raw).lower()
        risky = any(marker in scored for marker in _RISKY_MARKERS)
        token = "yes" if risky else "no"

        self._send_json(
            {
                "id": "chatcmpl-mock-guardian",
                "object": "chat.completion",
                "created": 1700000000,
                "model": "ibm-granite/granite-guardian-4.1-8b",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": f"</think><score>{token}</score>",
                        },
                        "finish_reason": "stop",
                        "logprobs": {"content": _score_logprobs(risky)},
                    }
                ],
            }
        )


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Mock Granite Guardian server on :{port}")
    server.serve_forever()

#!/usr/bin/env python3
"""Minimal mock OpenTelemetry (OTLP/HTTP) collector for E2E tests.

Accepts OTLP/HTTP exports from the Lightspeed Core Stack and buffers the raw
request bodies in memory so Behave steps can assert that telemetry was
delivered. Uses only the Python standard library.

Endpoints
---------
- ``POST /v1/traces``  : Receive an OTLP trace export (spans).
- ``POST /v1/logs``    : Receive an OTLP log export (log records / events).
- ``POST /v1/metrics`` : Receive an OTLP metric export.
  Each returns ``200`` with an empty ``application/x-protobuf`` body, which the
  OTLP/HTTP exporter accepts as success.
- ``GET /received``    : Return a JSON summary of everything buffered so far.
  With ``?contains=<text>`` it reports whether that substring appears in any
  buffered payload (raw-byte search; OTLP protobuf stores string fields as
  UTF-8, so a plaintext marker embedded in an attribute value is found).
- ``POST /reset``      : Clear the buffer (used at the start of a scenario).
- ``GET /health``      : Liveness probe returning ``{"status": "ok"}``.

Run as ``python server.py [port]``; default port is 4318 (OTLP/HTTP).

The exporter must be configured for HTTP/protobuf, e.g.::

    OTEL_EXPORTER_OTLP_ENDPOINT=http://mock-otel:4318
    OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

# OTLP/HTTP signal paths the exporter posts to.
_TRACES_PATH = "/v1/traces"
_LOGS_PATH = "/v1/logs"
_METRICS_PATH = "/v1/metrics"
_SIGNAL_PATHS = {
    _TRACES_PATH: "traces",
    _LOGS_PATH: "logs",
    _METRICS_PATH: "metrics",
}

# Buffered exports shared across handler threads: list of (signal, raw_body).
_received: list[tuple[str, bytes]] = []
_received_lock = threading.Lock()


def _record(signal: str, body: bytes) -> None:
    """Append a received export payload to the shared buffer."""
    with _received_lock:
        _received.append((signal, body))


def _reset() -> None:
    """Clear the shared buffer of received exports."""
    with _received_lock:
        _received.clear()


def _snapshot() -> list[tuple[str, bytes]]:
    """Return a copy of the buffered exports for lock-free inspection."""
    with _received_lock:
        return list(_received)


class Handler(BaseHTTPRequestHandler):
    """HTTP handler buffering OTLP exports and answering test queries."""

    def _send_json(self, status: int, data: dict) -> None:
        """Send a JSON response with the given status code."""
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_otlp_ok(self) -> None:
        """Acknowledge an OTLP export with an empty protobuf 200 response."""
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        """Serve the health probe and the buffered-data query endpoint."""
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        if parsed.path == "/received":
            self._handle_received_query(parsed.query)
            return
        self._send_json(404, {"error": "not found"})

    def _handle_received_query(self, query: str) -> None:
        """Answer a summary or substring query over the buffered exports."""
        received = _snapshot()
        signals: dict[str, int] = {}
        total_bytes = 0
        for signal, body in received:
            signals[signal] = signals.get(signal, 0) + 1
            total_bytes += len(body)

        params = parse_qs(query)
        contains = params.get("contains", [None])[0]
        if contains:
            needle = contains.encode("utf-8")
            matches = sum(1 for _, body in received if needle in body)
            self._send_json(
                200,
                {
                    "contains": contains,
                    "found": matches > 0,
                    "matches": matches,
                    "count": len(received),
                    "signals": signals,
                },
            )
            return

        self._send_json(
            200,
            {
                "count": len(received),
                "signals": signals,
                "total_bytes": total_bytes,
            },
        )

    def do_POST(self) -> None:  # pylint: disable=invalid-name
        """Buffer OTLP exports and handle the reset control endpoint."""
        parsed = urlparse(self.path)
        if parsed.path == "/reset":
            _reset()
            self._send_json(200, {"status": "reset"})
            return

        signal = _SIGNAL_PATHS.get(parsed.path)
        if signal is None:
            self._send_json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        _record(signal, body)
        self._send_otlp_ok()

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default request logging for minimal test output."""


def main() -> None:
    """Start the mock OTLP collector on the requested port."""
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4318
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Mock OTEL collector on :{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Minimal mock OpenTelemetry (OTLP/HTTP) collector for E2E tests.

Accepts OTLP/HTTP exports from the Lightspeed Core Stack and buffers the raw
request bodies in memory so Behave steps can assert that telemetry was
delivered. Uses only the Python standard library.

Endpoints
---------
- ``POST /v1/*``     : Receive an OTLP export (traces/logs/metrics). The body is
  buffered and the request is answered with an empty ``application/x-protobuf``
  200, which the OTLP/HTTP exporter accepts as success.
- ``GET /received``  : Report how many exports have been buffered. With
  ``?contains=<text>`` it reports whether that substring appears in any buffered
  payload (raw-byte search; OTLP protobuf stores string fields as UTF-8, so a
  plaintext marker embedded in an attribute value is found).
- ``POST /reset``    : Clear the buffer (used at the start of a scenario).
- ``GET /health``    : Liveness probe returning ``{"status": "ok"}``.

Run as ``python server.py [port]``; default port is 4318 (OTLP/HTTP).

The exporter must be configured for HTTP/protobuf, e.g.::

    OTEL_EXPORTER_OTLP_ENDPOINT=http://mock-otel:4318
    OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
"""

import json
import sys
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# Resource bounds so a reachable caller cannot exhaust process memory by sending
# large or repeated exports (the Compose service publishes port 4318). The
# per-body cap bounds each entry; the entry-count and total-byte caps bound the
# whole buffer (oldest entries are evicted first). With 1000 entries of up to
# 5 MiB each an unbounded buffer could reach ~5 GiB, so the total-byte cap is the
# effective ceiling.
_MAX_BODY_BYTES = 5 * 1024 * 1024  # reject a single OTLP body larger than 5 MiB
_MAX_ENTRIES = 1000  # keep at most this many buffered exports
_MAX_TOTAL_BYTES = 64 * 1024 * 1024  # keep at most this many bytes buffered
_SOCKET_READ_TIMEOUT_S = 30  # cap a single blocking body read

# Buffered export bodies shared across handler threads, oldest first. deque and
# its append/clear are thread-safe, but iteration and the running byte total are
# not, so reads and writes are guarded by a lock.
_received: "deque[bytes]" = deque()
_total_bytes = 0
_lock = threading.Lock()


def _record(body: bytes) -> None:
    """Buffer ``body``, evicting oldest entries to stay within the bounds.

    Must be called while holding ``_lock``.
    """
    global _total_bytes  # pylint: disable=global-statement
    _received.append(body)
    _total_bytes += len(body)
    while _received and (
        len(_received) > _MAX_ENTRIES or _total_bytes > _MAX_TOTAL_BYTES
    ):
        _total_bytes -= len(_received.popleft())


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

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        """Serve the health probe and the buffered-data query endpoint."""
        path, _, query = self.path.partition("?")
        if path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        if path == "/received":
            self._handle_received_query(query)
            return
        self._send_json(404, {"error": "not found"})

    def _handle_received_query(self, query: str) -> None:
        """Answer a count or substring query over the buffered exports."""
        contains = None
        for pair in query.split("&"):
            key, sep, value = pair.partition("=")
            if sep and key == "contains":
                contains = value
                break

        if contains is not None:
            needle = contains.encode("utf-8")
            with _lock:
                matches = sum(1 for body in _received if needle in body)
                count = len(_received)
            self._send_json(
                200,
                {
                    "contains": contains,
                    "found": matches > 0,
                    "matches": matches,
                    "count": count,
                },
            )
            return

        with _lock:
            count = len(_received)
        self._send_json(200, {"count": count})

    def do_POST(self) -> None:  # pylint: disable=invalid-name
        """Buffer OTLP exports and handle the reset control endpoint."""
        path, _, _ = self.path.partition("?")
        if path == "/reset":
            global _total_bytes  # pylint: disable=global-statement
            with _lock:
                _received.clear()
                _total_bytes = 0
            self._send_json(200, {"status": "reset"})
            return

        # Any other POST is treated as an OTLP export (e.g. /v1/traces).
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            self._send_json(400, {"error": "invalid content-length"})
            return
        if length < 0 or length > _MAX_BODY_BYTES:
            self._send_json(413, {"error": "payload too large"})
            return

        # Bound the blocking read so a client that advertises a Content-Length but
        # stalls mid-body cannot tie up a handler thread indefinitely. ``length``
        # is a validated non-negative int here; skip the read for a zero-length
        # body so it becomes b"".
        self.connection.settimeout(_SOCKET_READ_TIMEOUT_S)
        try:
            body = self.rfile.read(length) if length > 0 else b""
        except (TimeoutError, OSError):
            self._send_json(408, {"error": "request timeout"})
            return
        with _lock:
            _record(body)

        # Acknowledge with an empty protobuf 200, which the OTLP exporter accepts.
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", "0")
        self.end_headers()

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

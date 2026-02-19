#!/usr/bin/env python3
"""Minimal mock MCP server for E2E tests with OAuth support.

Responds to GET (OAuth probe) with 401 and WWW-Authenticate. Accepts POST
(MCP JSON-RPC) when Authorization: Bearer <token> is present; otherwise 401.
Uses only Python stdlib.
"""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any

# Standard OAuth-style challenge so the client can drive an OAuth flow
WWW_AUTHENTICATE = 'Bearer realm="mock-mcp", error="invalid_token"'


class Handler(BaseHTTPRequestHandler):
    """HTTP handler: GET/POST without valid Bearer → 401; POST with Bearer → MCP."""

    def _require_oauth(self) -> None:
        """Send 401 with WWW-Authenticate."""
        self.send_response(401)
        self.send_header("WWW-Authenticate", WWW_AUTHENTICATE)
        self.send_header("Content-Type", "application/json")
        body = b'{"error":"unauthorized"}'
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _parse_auth(self) -> str | None:
        """Return Bearer token if present, else None."""
        auth = self.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            return auth[7:].strip()
        return None

    def _json_response(self, data: dict) -> None:
        """Send JSON response."""
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        """Handle GET requests."""
        if self.path == "/health":
            self._json_response({"status": "ok"})
        else:
            self._require_oauth()

    def do_POST(self) -> None:  # pylint: disable=invalid-name
        """Handle POST requests."""
        if self._parse_auth() is None:
            self._require_oauth()
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(raw.decode("utf-8"))
            req_id = req.get("id", 1)
            method = req.get("method", "")
        except (json.JSONDecodeError, UnicodeDecodeError):
            req_id = 1
            method = ""

        if method == "initialize":
            self._json_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "mock-mcp-e2e", "version": "1.0.0"},
                    },
                }
            )
        elif method == "tools/list":
            self._json_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {
                                "name": "mock_tool",
                                "description": "Mock tool for E2E",
                                "inputSchema": {"type": "object"},
                            }
                        ],
                    },
                }
            )
        else:
            self._json_response({"jsonrpc": "2.0", "id": req_id, "result": {}})

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress request logging for minimal output."""


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 3000), Handler)
    print("Mock MCP server on :3000")
    server.serve_forever()

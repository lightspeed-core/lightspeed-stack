#!/usr/bin/env python3
"""Minimal mock MCP server for E2E tests with optional OAuth support.

By default, requires Bearer authentication on every request (except /health).
Pass ``--no-auth`` to disable authentication and serve all requests openly.

Run as ``python server.py [--port PORT] [--no-auth]``; default port is 3000.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional

# Standard OAuth-style challenge so the client can drive an OAuth flow
WWW_AUTHENTICATE = 'Bearer realm="mock-mcp", error="invalid_token"'

_TWO_NUMBER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "a": {"type": "number", "description": "First operand"},
        "b": {"type": "number", "description": "Second operand"},
    },
    "required": ["a", "b"],
}


def _math_tool_schemas() -> list[dict]:
    """Return MCP tool descriptors for the four arithmetic operations."""
    return [
        {
            "name": "add",
            "description": "Add two numbers",
            "inputSchema": _TWO_NUMBER_SCHEMA,
        },
        {
            "name": "subtract",
            "description": "Subtract two numbers (a - b)",
            "inputSchema": _TWO_NUMBER_SCHEMA,
        },
        {
            "name": "multiply",
            "description": "Multiply two numbers",
            "inputSchema": _TWO_NUMBER_SCHEMA,
        },
        {
            "name": "divide",
            "description": "Divide two numbers (a / b)",
            "inputSchema": _TWO_NUMBER_SCHEMA,
        },
    ]


class Handler(BaseHTTPRequestHandler):
    """HTTP handler for MCP JSON-RPC with optional Bearer auth."""

    require_auth: bool = True

    def _require_oauth(self) -> None:
        """Send 401 with WWW-Authenticate."""
        self.send_response(401)
        self.send_header("WWW-Authenticate", WWW_AUTHENTICATE)
        self.send_header("Content-Type", "application/json")
        body = b'{"error":"unauthorized"}'
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _parse_auth(self) -> Optional[str]:
        """Return Bearer token if present, else None.

        When ``require_auth`` is False, always returns a sentinel value so
        every request is treated as authenticated.
        """
        if not self.require_auth:
            return "no-auth"
        auth = self.headers.get("Authorization")
        if auth and auth.startswith("Bearer ") and "invalid" not in auth:
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
        path_only = self.path.split("?", 1)[0]
        if path_only == "/health":
            self._json_response({"status": "ok"})
        elif self._parse_auth() is not None:
            self._json_response({"status": "authorized"})
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
        except (json.JSONDecodeError, UnicodeDecodeError):
            req = {}
        req_id = req.get("id", 1)
        method = req.get("method", "")

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
                                "name": "mock_tool_e2e",
                                "description": "Mock tool for E2E",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "message": {
                                            "type": "string",
                                            "description": "Test message",
                                        }
                                    },
                                },
                            },
                            *_math_tool_schemas(),
                        ],
                    },
                }
            )
        elif method == "tools/call":
            self._handle_tool_call(req, req_id)
        else:
            self._json_response({"jsonrpc": "2.0", "id": req_id, "result": {}})

    def _handle_tool_call(self, req: dict, req_id: int) -> None:
        """Dispatch tools/call requests to the appropriate handler."""
        params = req.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        ops = {
            "add": lambda a, b: a + b,
            "subtract": lambda a, b: a - b,
            "multiply": lambda a, b: a * b,
            "divide": lambda a, b: a / b,
        }

        if tool_name in ops:
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            if tool_name == "divide" and b == 0:
                self._json_response(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {"type": "text", "text": "Error: division by zero"}
                            ],
                            "isError": True,
                        },
                    }
                )
                return
            result = ops[tool_name](a, b)
            self._json_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": str(result)}],
                    },
                }
            )
        else:
            self._json_response(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": f"Unknown tool: {tool_name}"}
                        ],
                        "isError": True,
                    },
                }
            )

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress request logging for minimal output."""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mock MCP server for E2E tests")
    parser.add_argument("--port", type=int, default=3000, help="Port to listen on")
    parser.add_argument(
        "--no-auth",
        action="store_true",
        default=False,
        help="Disable Bearer authentication",
    )
    # Legacy positional port for backward compatibility
    parser.add_argument("legacy_port", nargs="?", type=int, default=None)
    args = parser.parse_args()

    port = args.legacy_port if args.legacy_port is not None else args.port
    Handler.require_auth = not args.no_auth

    mode = "open (no auth)" if args.no_auth else "auth required"
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Mock MCP server on :{port} [{mode}]")
    server.serve_forever()

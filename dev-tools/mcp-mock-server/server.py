#!/usr/bin/env python3
"""Minimal MCP mock server for testing authorization headers.

This is a simple HTTP/HTTPS server that implements basic MCP protocol endpoints
for testing purposes. It captures and logs authorization headers, making it
useful for validating that Lightspeed Core Stack correctly sends auth headers
to MCP servers.

The server runs HTTP and optionally HTTPS on consecutive ports.
Set MCP_HTTP_ONLY=true to disable HTTPS (useful when openssl is unavailable).

Usage:
    python server.py [http_port]

Example:
    python server.py 3000  # HTTP on 3000, HTTPS on 3001
    MCP_HTTP_ONLY=true python server.py 3000  # HTTP only on 3000
"""

import json
import os
import ssl
import subprocess
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from pathlib import Path
from typing import Any

# Global storage for captured headers (last request)
last_headers: dict[str, str] = {}
request_log: list = []


class MCPMockHandler(BaseHTTPRequestHandler):
    """HTTP request handler for mock MCP server."""

    def log_message(self, format: str, *args: Any) -> None:
        """Log requests with timestamp."""  # pylint: disable=redefined-builtin
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {format % args}")

    def _capture_headers(self) -> None:
        """Capture all headers from the request."""
        last_headers.clear()

        # Capture all headers for debugging
        for header_name, value in self.headers.items():
            last_headers[header_name] = value

        # Log the request
        request_log.append(
            {
                "timestamp": datetime.now().isoformat(),
                "method": self.command,
                "path": self.path,
                "headers": dict(last_headers),
            }
        )

        # Keep only last 10 requests
        if len(request_log) > 10:
            request_log.pop(0)

    def do_POST(self) -> None:  # pylint: disable=invalid-name
        """Handle POST requests (MCP protocol endpoints)."""
        self._capture_headers()

        # Read request body to get JSON-RPC request
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            request_data = json.loads(body.decode("utf-8"))
            request_id = request_data.get("id", 1)
            method = request_data.get("method", "unknown")
        except (json.JSONDecodeError, UnicodeDecodeError):
            request_id = 1
            method = "unknown"

        # Determine tool name based on authorization header to avoid collisions
        auth_header = self.headers.get("Authorization", "")

        # Match based on token content
        match auth_header:
            case _ if "test-secret-token" in auth_header:
                tool_name = "mock_tool_file"
                tool_desc = "Mock tool with file-based auth"
            case _ if "my-k8s-token" in auth_header:
                tool_name = "mock_tool_k8s"
                tool_desc = "Mock tool with Kubernetes token"
            case _ if "my-client-token" in auth_header:
                tool_name = "mock_tool_client"
                tool_desc = "Mock tool with client-provided token"
            case _:
                # No auth header or unrecognized token
                tool_name = "mock_tool_no_auth"
                tool_desc = "Mock tool with no authorization"

        # Handle MCP protocol methods
        if method == "initialize":
            # Return MCP initialize response
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                    },
                    "serverInfo": {
                        "name": "mock-mcp-server",
                        "version": "1.0.0",
                    },
                },
            }
        elif method == "tools/list":
            # Return list of tools with unique name
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": tool_name,
                            "description": tool_desc,
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "message": {
                                        "type": "string",
                                        "description": "Test message",
                                    }
                                },
                            },
                        }
                    ]
                },
            }
        else:
            # Generic success response for other methods
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"status": "ok"},
            }

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

        print(f"  → Captured headers: {last_headers}")

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        """Handle GET requests (debug endpoints)."""
        # Handle different GET endpoints
        match self.path:
            case "/debug/headers":
                self._send_json_response(
                    {"last_headers": last_headers, "request_count": len(request_log)}
                )
            case "/debug/requests":
                self._send_json_response(request_log)
            case "/":
                self._send_help_page()
            case _:
                self.send_response(404)
                self.end_headers()

    def _send_json_response(self, data: dict | list) -> None:
        """Send a JSON response."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def _send_help_page(self) -> None:
        """Send HTML help page for root endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        help_html = """<!DOCTYPE html>
        <html>
        <head><title>MCP Mock Server</title></head>
        <body>
            <h1>MCP Mock Server</h1>
            <p>Development mock server for testing MCP integrations.</p>
            <h2>Debug Endpoints:</h2>
            <ul>
                <li><a href="/debug/headers">/debug/headers</a> - View captured headers</li>
                <li><a href="/debug/requests">/debug/requests</a> - View request log</li>
            </ul>
            <h2>MCP Protocol:</h2>
            <p>POST requests to any path with JSON-RPC format:</p>
            <ul>
                <li><code>{"jsonrpc": "2.0", "id": 1, "method": "initialize"}</code></li>
                <li><code>{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}</code></li>
            </ul>
        </body>
        </html>
        """
        self.wfile.write(help_html.encode())


def generate_self_signed_cert(cert_dir: Path) -> tuple[Path, Path]:
    """Generate self-signed certificate for HTTPS testing.

    Args:
        cert_dir: Directory to store certificate files

    Returns:
        Tuple of (cert_file, key_file) paths
    """
    cert_file = cert_dir / "cert.pem"
    key_file = cert_dir / "key.pem"

    # Only generate if files don't exist
    if cert_file.exists() and key_file.exists():
        return cert_file, key_file

    cert_dir.mkdir(parents=True, exist_ok=True)

    # Generate self-signed certificate using openssl
    try:
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:4096",
                "-keyout",
                str(key_file),
                "-out",
                str(cert_file),
                "-days",
                "365",
                "-nodes",
                "-subj",
                "/CN=localhost",
            ],
            check=True,
            capture_output=True,
        )
        print(f"Generated self-signed certificate: {cert_file}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to generate certificate: {e}")
        raise

    return cert_file, key_file


def run_http_server(port: int, httpd: HTTPServer) -> None:
    """Run HTTP server in a thread."""
    print(f"HTTP server started on http://localhost:{port}")
    try:
        httpd.serve_forever()
    except Exception as e:  # pylint: disable=broad-except
        print(f"HTTP server error: {e}")


def run_https_server(port: int, httpd: HTTPServer) -> None:
    """Run HTTPS server in a thread."""
    print(f"HTTPS server started on https://localhost:{port}")
    try:
        httpd.serve_forever()
    except Exception as e:  # pylint: disable=broad-except
        print(f"HTTPS server error: {e}")


def main() -> None:  # pylint: disable=R0915
    """Start the mock MCP server with HTTP and optionally HTTPS."""
    http_port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    http_only = os.environ.get("MCP_HTTP_ONLY", "").lower() in ("true", "1", "yes")

    # Create HTTP server
    http_server = HTTPServer(("", http_port), MCPMockHandler)

    https_server = None
    https_port = -1
    if not http_only:
        try:
            https_port = http_port + 1
            https_server = HTTPServer(("", https_port), MCPMockHandler)

            # Generate or load self-signed certificate
            script_dir = Path(__file__).parent
            cert_dir = script_dir / ".certs"
            cert_file, key_file = generate_self_signed_cert(cert_dir)

            # Wrap socket with SSL
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert_file, key_file)
            https_server.socket = context.wrap_socket(
                https_server.socket, server_side=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
            print(f"HTTPS setup failed ({e}), running HTTP only")
            https_server = None

    print("=" * 70)
    if https_server:
        print("MCP Mock Server starting with HTTP and HTTPS")
    else:
        print("MCP Mock Server starting (HTTP only)")
    print("=" * 70)
    print(f"HTTP:  http://localhost:{http_port}")
    if https_server:
        print(f"HTTPS: https://localhost:{https_port}")
    print("=" * 70)
    print("Debug endpoints:")
    print("  • /debug/headers  - View captured headers")
    print("  • /debug/requests - View request log")
    print("MCP endpoint:")
    print("  • POST to any path (e.g., / or /mcp/v1/list_tools)")
    print("=" * 70)
    if https_server:
        print("Note: HTTPS uses a self-signed certificate (for testing only)")
    print("Press Ctrl+C to stop")
    print()

    # Start HTTP server in a thread
    http_thread = threading.Thread(
        target=run_http_server, args=(http_port, http_server), daemon=True
    )
    http_thread.start()

    # Start HTTPS server if available
    https_thread = None
    if https_server:
        https_thread = threading.Thread(
            target=run_https_server, args=(https_port, https_server), daemon=True
        )
        https_thread.start()

    try:
        # Keep main thread alive
        http_thread.join()
        if https_thread:
            https_thread.join()
    except KeyboardInterrupt:
        print("\nShutting down mock servers...")
        http_server.shutdown()
        if https_server:
            https_server.shutdown()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Mock OpenAI-compatible HTTPS inference server for TLS e2e testing.

Serves two HTTPS listeners using trustme-generated test certificates:
  - Port 8443: standard TLS (no client certificate required)
  - Port 8444: mutual TLS (client certificate required, verified against CA)

Implements the minimal OpenAI API surface needed by Llama Stack's
remote::openai provider: /v1/models and /v1/chat/completions.

Certificates are generated on-the-fly using trustme at server startup.
"""

import datetime
import json
import os
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import trustme
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509 import CertificateBuilder, random_serial_number

MODEL_ID = "mock-tls-model"
TLS_PORT = 8443
MTLS_PORT = 8444
HOSTNAME_MISMATCH_PORT = 8445

_DEFAULT_SERVER_CERT_DNS_NAMES: tuple[str, ...] = (
    "mock-tls-inference",
    "localhost",
    "127.0.0.1",
)


def _server_cert_dns_names() -> tuple[str, ...]:
    """Return DNS identities for the main server certificate.

    Reads comma-separated ``TLS_CERT_DNS_NAMES`` (set in Konflux/Prow manifest).
    Falls back to Docker Compose defaults when unset.
    """
    raw = os.environ.get("TLS_CERT_DNS_NAMES", "").strip()
    if not raw:
        return _DEFAULT_SERVER_CERT_DNS_NAMES
    names = tuple(name.strip() for name in raw.split(",") if name.strip())
    return names or _DEFAULT_SERVER_CERT_DNS_NAMES


class OpenAIHandler(BaseHTTPRequestHandler):
    """Handles OpenAI-compatible API requests over HTTPS."""

    def log_message(
        self, format: str, *args: Any
    ) -> None:  # pylint: disable=redefined-builtin
        """Timestamp log output."""
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {format % args}")

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        """Handle GET requests."""
        if self.path == "/health":
            self._send_json({"status": "ok"})
        elif self.path == "/v1/models":
            self._send_json(
                {
                    "object": "list",
                    "data": [
                        {
                            "id": MODEL_ID,
                            "object": "model",
                            "created": 1700000000,
                            "owned_by": "test",
                        }
                    ],
                }
            )
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # pylint: disable=invalid-name
        """Handle POST requests (chat completions)."""
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            request_data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            request_data = {}

        model = request_data.get("model", MODEL_ID)
        completion_id = "chatcmpl-tls-test-001"
        response_text = "Hello from the TLS mock inference server."

        # Llama Stack calls remote chat completions with stream=True and reads
        # assistant text from delta.content chunks.
        if request_data.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            content_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": 1700000000,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": response_text},
                        "finish_reason": None,
                    }
                ],
            }
            self.wfile.write(f"data: {json.dumps(content_chunk)}\n\n".encode())
            finish_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": 1700000000,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 8,
                    "completion_tokens": 9,
                    "total_tokens": 17,
                },
            }
            self.wfile.write(f"data: {json.dumps(finish_chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            return

        self._send_json(
            {
                "id": completion_id,
                "object": "chat.completion",
                "created": 1700000000,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": response_text,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 8,
                    "completion_tokens": 9,
                    "total_tokens": 17,
                },
            }
        )

    def _send_json(self, data: dict | list) -> None:
        """Write a JSON response."""
        payload = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _export_expired_client_cert(
    ca: trustme.CA, client_cert: trustme.LeafCert, path: Path
) -> None:
    """Re-sign a client certificate with expired validity dates.

    Parameters:
    ----------
        ca: The CA that issued the original client certificate.
        client_cert: The original client leaf certificate.
        path: File path to write the expired client certificate PEM.

    Note:
        Accesses ca._private_key which is a private attribute of trustme.CA.
        This is fragile and may break if trustme changes its internal implementation.
        No public API exists in trustme for re-signing certs with custom validity.
    """
    original = client_cert.cert_chain_pems[0].bytes()
    from cryptography.x509 import load_pem_x509_certificate

    orig_cert = load_pem_x509_certificate(original)
    now = datetime.datetime.now(datetime.UTC)
    builder = CertificateBuilder()
    builder = builder.subject_name(orig_cert.subject)
    builder = builder.issuer_name(orig_cert.issuer)
    builder = builder.public_key(orig_cert.public_key())
    builder = builder.serial_number(random_serial_number())
    builder = builder.not_valid_before(now - datetime.timedelta(days=365))
    builder = builder.not_valid_after(now - datetime.timedelta(seconds=1))
    for ext in orig_cert.extensions:
        builder = builder.add_extension(ext.value, ext.critical)
    expired_cert = builder.sign(ca._private_key, hashes.SHA256())
    path.write_bytes(expired_cert.public_bytes(serialization.Encoding.PEM))


def _export_expired_ca_cert(ca: trustme.CA, path: Path) -> None:
    """Re-sign a trustme CA certificate with expired validity dates.

    Creates a copy of the CA's self-signed certificate but with validity
    dates set in the past, making it an expired certificate.

    Parameters:
    ----------
        ca: The trustme CA whose certificate and key to use.
        path: File path to write the expired CA certificate PEM.

    Note:
        Accesses ca._certificate and ca._private_key which are private attributes
        of trustme.CA. This is fragile and may break if trustme changes its
        internal implementation. No public API exists for re-signing with custom validity.
    """
    original = ca._certificate
    now = datetime.datetime.now(datetime.UTC)
    builder = CertificateBuilder()
    builder = builder.subject_name(original.subject)
    builder = builder.issuer_name(original.issuer)
    builder = builder.public_key(original.public_key())
    builder = builder.serial_number(random_serial_number())
    builder = builder.not_valid_before(now - datetime.timedelta(days=365))
    builder = builder.not_valid_after(now - datetime.timedelta(seconds=1))
    for ext in original.extensions:
        builder = builder.add_extension(ext.value, ext.critical)
    expired_cert = builder.sign(ca._private_key, hashes.SHA256())
    path.write_bytes(expired_cert.public_bytes(serialization.Encoding.PEM))


def _make_tls_context(
    ca: trustme.CA,
    server_cert: trustme.LeafCert,
    require_client_cert: bool = False,
) -> ssl.SSLContext:
    """Build an SSL context using trustme-generated certificates.

    Parameters:
    ----------
        ca: The trustme CA instance.
        server_cert: The server certificate issued by the CA.
        require_client_cert: Whether to require client certificate (mTLS).

    Returns:
    -------
        Configured SSL context for server-side TLS.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_cert.configure_cert(ctx)
    if require_client_cert:
        ctx.verify_mode = ssl.CERT_REQUIRED
        ca.configure_trust(ctx)
    return ctx


def _run_server(httpd: ThreadingHTTPServer, label: str) -> None:
    """Serve requests forever in a daemon thread."""
    print(f"{label} listening")
    try:
        httpd.serve_forever()
    except Exception as exc:  # pylint: disable=broad-except
        print(f"{label} error: {exc}")


def main() -> None:
    """Start standard-TLS (8443) and mTLS (8444) listeners.

    Generates certificates on-the-fly using trustme and exports the CA cert
    to /certs/ca.crt and client cert to /certs/client.* for use by tests.
    """
    print("=" * 60)
    print("Generating TLS certificates with trustme...")
    print("=" * 60)

    # Generate CA and certificates
    ca = trustme.CA()
    server_dns_names = _server_cert_dns_names()
    print(f"  Server cert DNS names: {', '.join(server_dns_names)}")
    server_cert = ca.issue_cert(*server_dns_names)
    # Client cert for mTLS testing (use a simple hostname without spaces)
    client_cert = ca.issue_cert("tls-e2e-test-client")

    # Export certificates to /certs directory for access by tests
    certs_dir = Path("/certs")
    certs_dir.mkdir(exist_ok=True, parents=True)

    # Export CA certificate
    ca.cert_pem.write_to_path(str(certs_dir / "ca.crt"))
    print(f"  CA cert: {certs_dir / 'ca.crt'}")

    # Export client certificate and key for mTLS tests
    client_cert.private_key_pem.write_to_path(str(certs_dir / "client.key"))
    # Write certificate chain (may include multiple certs)
    with (certs_dir / "client.crt").open("wb") as f:
        for blob in client_cert.cert_chain_pems:
            f.write(blob.bytes())
    print(f"  Client cert: {certs_dir / 'client.crt'}")
    print(f"  Client key: {certs_dir / 'client.key'}")

    # Export untrusted CA certificate (from a separate CA that did not sign the server cert)
    untrusted_ca = trustme.CA()
    untrusted_ca.cert_pem.write_to_path(str(certs_dir / "untrusted-ca.crt"))
    print(f"  Untrusted CA cert: {certs_dir / 'untrusted-ca.crt'}")

    # Export expired CA certificate (re-signed with past validity dates)
    _export_expired_ca_cert(ca, certs_dir / "expired-ca.crt")
    print(f"  Expired CA cert: {certs_dir / 'expired-ca.crt'}")

    # Export untrusted client certificate (issued by a different CA)
    untrusted_client = untrusted_ca.issue_cert("tls-e2e-untrusted-client")
    untrusted_client.private_key_pem.write_to_path(
        str(certs_dir / "untrusted-client.key")
    )
    with (certs_dir / "untrusted-client.crt").open("wb") as f:
        for blob in untrusted_client.cert_chain_pems:
            f.write(blob.bytes())
    print(f"  Untrusted client cert: {certs_dir / 'untrusted-client.crt'}")

    # Export expired client certificate (signed by main CA but with past dates)
    _export_expired_client_cert(ca, client_cert, certs_dir / "expired-client.crt")
    print(f"  Expired client cert: {certs_dir / 'expired-client.crt'}")

    # Issue a server cert with a hostname that does NOT match the Docker service
    # name ("mock-tls-inference") — used to test hostname-mismatch rejection.
    hostname_mismatch_cert = ca.issue_cert("wrong-hostname.example.com")
    print("  Hostname-mismatch server cert: wrong-hostname.example.com (port 8445)")

    print("=" * 60)
    print("Starting servers...")
    print("=" * 60)

    # Create TLS server (no client cert required)
    tls_server = ThreadingHTTPServer(("", TLS_PORT), OpenAIHandler)
    tls_ctx = _make_tls_context(ca, server_cert, require_client_cert=False)
    tls_server.socket = tls_ctx.wrap_socket(tls_server.socket, server_side=True)

    # Create mTLS server (client cert required)
    mtls_server = ThreadingHTTPServer(("", MTLS_PORT), OpenAIHandler)
    mtls_ctx = _make_tls_context(ca, server_cert, require_client_cert=True)
    mtls_server.socket = mtls_ctx.wrap_socket(mtls_server.socket, server_side=True)

    # Create hostname-mismatch TLS server (cert SAN ≠ connecting hostname)
    mismatch_server = ThreadingHTTPServer(("", HOSTNAME_MISMATCH_PORT), OpenAIHandler)
    mismatch_ctx = _make_tls_context(
        ca, hostname_mismatch_cert, require_client_cert=False
    )
    mismatch_server.socket = mismatch_ctx.wrap_socket(
        mismatch_server.socket, server_side=True
    )

    print("=" * 60)
    print("Mock TLS Inference Server")
    print("=" * 60)
    print(f"  TLS      : https://localhost:{TLS_PORT}  (no client cert)")
    print(f"  mTLS     : https://localhost:{MTLS_PORT}  (client cert required)")
    print(
        f"  Mismatch : https://localhost:{HOSTNAME_MISMATCH_PORT}"
        "  (hostname-mismatch cert)"
    )
    print(f"  Model: {MODEL_ID}")
    print("=" * 60)

    for srv, label in [
        (tls_server, f"TLS  :{TLS_PORT}"),
        (mtls_server, f"mTLS :{MTLS_PORT}"),
        (mismatch_server, f"Mismatch :{HOSTNAME_MISMATCH_PORT}"),
    ]:
        t = threading.Thread(target=_run_server, args=(srv, label), daemon=True)
        t.start()

    # Keep main thread alive (daemon threads run until container stops)
    threading.Event().wait()


if __name__ == "__main__":
    main()

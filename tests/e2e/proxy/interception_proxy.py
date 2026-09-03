"""Minimal TLS-intercepting (MITM) proxy for e2e testing.

Implements a proxy that terminates TLS from the client, inspects the traffic,
and re-encrypts toward the destination using trustme-generated certificates.
This simulates a corporate interception proxy (SSL inspection).

Local Behave usage::

    import trustme
    ca = trustme.CA()
    proxy = InterceptionProxy(ca=ca, port=8889)
    await proxy.start()
    # ... run tests with proxy URL and ca_cert_path pointing to the trustme CA ...
    await proxy.stop()
    assert proxy.intercepted_hosts  # verify interception happened

In-cluster (Konflux/Prow) usage::

    python interception_proxy.py
    # MITM on 8889; GET http://127.0.0.1:8886/stats for counters;
    # CA PEM at /tmp/interception-proxy-ca.pem (copy into llama-stack pod).
"""

import asyncio
import json
import logging
import ssl
from pathlib import Path
from typing import Any, Optional

import trustme

logger = logging.getLogger(__name__)

DEFAULT_INTERCEPTION_PROXY_PORT = 8889
DEFAULT_INTERCEPTION_STATS_PORT = 8886
# Local Behave: second listener for "without CA" scenarios; in-cluster maps to 8889.
ALTERNATE_INTERCEPTION_PROXY_PORT = 8890
IN_CLUSTER_CA_CERT_PATH = Path("/tmp/interception-proxy-ca.pem")


class InterceptionProxy:
    """Async TLS-intercepting proxy for testing.

    Attributes:
        host: Bind address for the proxy server.
        port: Port to listen on.
        ca: The trustme CA used to generate interception certificates.
        intercepted_hosts: Set of host:port targets that were intercepted.
        connect_count: Number of CONNECT requests handled.
    """

    def __init__(
        self,
        ca: trustme.CA,
        host: str = "127.0.0.1",
        port: int = 8889,
    ) -> None:
        """Initialize interception proxy."""
        self.host = host
        self.port = port
        self.ca = ca
        self.intercepted_hosts: set[str] = set()
        self.connect_count = 0
        self._server: Optional[asyncio.Server] = None
        self._handler_tasks: set[asyncio.Task[Any]] = set()

    def _make_server_ssl_context(self, hostname: str) -> ssl.SSLContext:
        """Create an SSL context with a certificate for the given hostname.

        Parameters:
        ----------
            hostname: The hostname to generate a certificate for.

        Returns:
        -------
            An ssl.SSLContext configured for server-side TLS with a cert
            signed by the proxy's CA for the given hostname.
        """
        server_cert = self.ca.issue_cert(hostname)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_cert.configure_cert(ctx)
        self.ca.configure_trust(ctx)
        return ctx

    @staticmethod
    def _parse_target(target: str) -> tuple[str, int]:
        """Parse a host:port target string."""
        if ":" in target:
            host, port_str = target.rsplit(":", 1)
            return host, int(port_str)
        return target, 443

    async def _upgrade_to_tls(
        self,
        writer: asyncio.StreamWriter,
        hostname: str,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Upgrade a plaintext connection to TLS (server-side)."""
        server_ctx = self._make_server_ssl_context(hostname)
        transport = writer.transport
        loop = asyncio.get_event_loop()

        new_transport = await loop.start_tls(
            transport, transport.get_protocol(), server_ctx, server_side=True
        )
        assert new_transport is not None, "TLS handshake failed"

        tls_reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(tls_reader)
        new_transport.set_protocol(protocol)
        protocol.connection_made(new_transport)
        tls_writer = asyncio.StreamWriter(
            new_transport, protocol, tls_reader, loop  # type: ignore[arg-type]
        )
        return tls_reader, tls_writer

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle an incoming client connection."""
        handle_task = asyncio.current_task()
        if handle_task is not None:
            self._handler_tasks.add(handle_task)
        try:
            await self._handle_client_inner(reader, writer)
        finally:
            if handle_task is not None:
                self._handler_tasks.discard(handle_task)

    async def _handle_client_inner(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle an incoming client connection (body)."""
        try:
            request_line = await reader.readline()
            if not request_line:
                return

            parts = request_line.decode("utf-8", errors="replace").strip().split()

            if len(parts) < 2 or parts[0].upper() != "CONNECT":
                writer.write(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
                await writer.drain()
                return

            target = parts[1]
            self.connect_count += 1
            self.intercepted_hosts.add(target)
            target_host, target_port = self._parse_target(target)

            # Read and discard remaining headers
            while True:
                header_line = await reader.readline()
                if header_line in (b"\r\n", b"\n", b""):
                    break

            # Send 200 to tell client to start TLS
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()

            # Upgrade client connection to TLS
            tls_reader, tls_writer = await self._upgrade_to_tls(writer, target_host)

            # Connect to the real server with TLS
            try:
                remote_reader, remote_writer = await asyncio.open_connection(
                    target_host, target_port, ssl=True
                )
            except (OSError, ConnectionRefusedError, ssl.SSLError) as e:
                logger.warning("Failed to connect to %s: %s", target, e)
                tls_writer.close()
                return

            logger.info("Intercepting connection to %s", target)

            # Bidirectional relay over the two TLS connections
            await asyncio.gather(
                self._relay(tls_reader, remote_writer),
                self._relay(remote_reader, tls_writer),
                return_exceptions=True,
            )

            remote_writer.close()
            tls_writer.close()

        except (
            ConnectionResetError,
            BrokenPipeError,
            asyncio.IncompleteReadError,
            ssl.SSLError,
        ):
            pass
        finally:
            writer.close()

    @staticmethod
    async def _relay(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Relay data from reader to writer until EOF."""
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass

    async def start(self) -> None:
        """Start the interception proxy server."""
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        logger.info("Interception proxy listening on %s:%d", self.host, self.port)

    async def stop(self) -> None:
        """Stop the interception proxy server."""
        if self._server is None:
            return
        self._server.close()
        for task in list(self._handler_tasks):
            if not task.done():
                task.cancel()
        if self._handler_tasks:
            await asyncio.gather(*self._handler_tasks, return_exceptions=True)
        await self._server.wait_closed()
        self._server = None
        self._handler_tasks.clear()
        logger.info("Interception proxy stopped")

    def export_ca_cert(self, path: Path) -> None:
        """Export the CA certificate to a PEM file.

        Parameters:
        ----------
            path: File path to write the CA certificate PEM to.
        """
        self.ca.cert_pem.write_to_path(str(path))
        logger.info("Exported interception proxy CA cert to %s", path)

    def reset_counters(self) -> None:
        """Reset request counters."""
        self.connect_count = 0
        self.intercepted_hosts.clear()


class _InterceptionStatsHandler:  # pylint: disable=too-few-public-methods
    """Expose interception proxy counters over HTTP for in-cluster e2e assertions."""

    def __init__(self, proxy: InterceptionProxy) -> None:
        self._proxy = proxy

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Serve ``GET /stats`` as JSON; other requests get 404."""
        try:
            request_line = await reader.readline()
            if not request_line:
                return
            line = request_line.decode("utf-8", errors="replace").strip()
            method_path = line.split()
            path = method_path[1] if len(method_path) > 1 else ""
            while True:
                header = await reader.readline()
                if header in (b"\r\n", b"\n", b""):
                    break
            if method_path and method_path[0].upper() == "GET" and path == "/stats":
                body = json.dumps(
                    {
                        "connect_count": self._proxy.connect_count,
                        "intercepted_hosts": sorted(self._proxy.intercepted_hosts),
                    }
                ).encode("utf-8")
                writer.write(b"HTTP/1.1 200 OK\r\n")
                writer.write(b"Content-Type: application/json\r\n")
                writer.write(f"Content-Length: {len(body)}\r\n\r\n".encode())
                writer.write(body)
            else:
                writer.write(b"HTTP/1.1 404 Not Found\r\n\r\n")
            await writer.drain()
        finally:
            writer.close()


async def _run_interception_stats_server(
    proxy: InterceptionProxy, host: str, port: int
) -> asyncio.Server:
    """Start the stats HTTP server bound to ``host:port``."""
    handler = _InterceptionStatsHandler(proxy)

    async def _client_handler(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await handler.handle(reader, writer)

    server = await asyncio.start_server(_client_handler, host, port)
    logger.info("Interception proxy stats listening on %s:%d", host, port)
    return server


async def run_in_cluster(
    proxy_port: int = DEFAULT_INTERCEPTION_PROXY_PORT,
    stats_port: int = DEFAULT_INTERCEPTION_STATS_PORT,
    ca_cert_path: Path = IN_CLUSTER_CA_CERT_PATH,
) -> None:
    """Run MITM proxy and stats server until cancelled (in-cluster pod entrypoint)."""
    ca = trustme.CA()
    proxy = InterceptionProxy(ca=ca, host="0.0.0.0", port=proxy_port)
    proxy.export_ca_cert(ca_cert_path)
    await proxy.start()
    stats_server = await _run_interception_stats_server(proxy, "0.0.0.0", stats_port)
    try:
        await asyncio.Event().wait()
    finally:
        stats_server.close()
        await stats_server.wait_closed()
        await proxy.stop()


def main() -> None:
    """CLI entrypoint for the ``e2e-interception-proxy`` Kubernetes pod."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_in_cluster())


if __name__ == "__main__":
    main()

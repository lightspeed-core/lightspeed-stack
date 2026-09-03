"""Minimal HTTP CONNECT tunnel proxy for e2e testing.

Implements a simple HTTP proxy that supports the CONNECT method for HTTPS
tunneling. The proxy creates a TCP tunnel between the client and the
destination server without inspecting the traffic.

Local Behave usage::

    proxy = TunnelProxy(port=8888)
    await proxy.start()
    # ... run tests with HTTPS_PROXY=http://localhost:8888 ...
    await proxy.stop()
    assert proxy.connect_count > 0  # verify proxy was used

In-cluster (Konflux/Prow) usage::

    python tunnel_proxy.py
    # CONNECT on 8888; GET http://127.0.0.1:8887/stats for connect_count JSON
"""

import asyncio
import json
import logging
from typing import Any, Optional

# In-cluster defaults (``python tunnel_proxy.py``).
DEFAULT_PROXY_PORT = 8888
DEFAULT_STATS_PORT = 8887

logger = logging.getLogger(__name__)


class TunnelProxy:
    """Async HTTP CONNECT tunnel proxy for testing.

    Attributes:
        host: Bind address for the proxy server.
        port: Port to listen on.
        connect_count: Number of CONNECT requests handled.
        last_connect_target: The last host:port that was tunneled to.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8888) -> None:
        """Initialize tunnel proxy configuration."""
        self.host = host
        self.port = port
        self.connect_count = 0
        self.last_connect_target: Optional[str] = None
        self._server: Optional[asyncio.Server] = None
        self._handler_tasks: set[asyncio.Task[Any]] = set()

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

            request_str = request_line.decode("utf-8", errors="replace").strip()
            parts = request_str.split()

            if len(parts) < 2:
                writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                await writer.drain()
                return

            method = parts[0].upper()

            if method != "CONNECT":
                writer.write(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
                await writer.drain()
                return

            target = parts[1]
            self.connect_count += 1
            self.last_connect_target = target

            # Parse target host:port
            if ":" in target:
                target_host, target_port_str = target.rsplit(":", 1)
                try:
                    target_port = int(target_port_str)
                except ValueError:
                    writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                    await writer.drain()
                    return
            else:
                target_host = target
                target_port = 443

            # Read and discard remaining headers
            while True:
                header_line = await reader.readline()
                if header_line in (b"\r\n", b"\n", b""):
                    break

            # Connect to the target with timeout
            try:
                remote_reader, remote_writer = await asyncio.wait_for(
                    asyncio.open_connection(target_host, target_port),
                    timeout=10,
                )
            except (asyncio.TimeoutError, OSError, ConnectionRefusedError) as e:
                logger.warning("Failed to connect to %s: %s", target, e)
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                await writer.drain()
                return

            # Send 200 Connection Established
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()

            logger.info("Tunnel established to %s", target)

            # Bidirectional relay
            await asyncio.gather(
                self._relay(reader, remote_writer),
                self._relay(remote_reader, writer),
                return_exceptions=True,
            )

            remote_writer.close()

        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
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
        """Start the proxy server."""
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        logger.info("Tunnel proxy listening on %s:%d", self.host, self.port)

    async def stop(self) -> None:
        """Stop the proxy server."""
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
        logger.info("Tunnel proxy stopped")

    def reset_counters(self) -> None:
        """Reset request counters."""
        self.connect_count = 0
        self.last_connect_target = None


class _StatsHandler:  # pylint: disable=too-few-public-methods
    """Expose tunnel proxy counters over HTTP for in-cluster e2e assertions."""

    def __init__(self, proxy: TunnelProxy) -> None:
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
                        "last_connect_target": self._proxy.last_connect_target,
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


async def _run_stats_server(proxy: TunnelProxy, host: str, port: int) -> asyncio.Server:
    """Start the stats HTTP server bound to ``host:port``."""
    handler = _StatsHandler(proxy)

    async def _client_handler(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await handler.handle(reader, writer)

    server = await asyncio.start_server(_client_handler, host, port)
    logger.info("Tunnel proxy stats listening on %s:%d", host, port)
    return server


async def run_in_cluster(
    proxy_port: int = DEFAULT_PROXY_PORT,
    stats_port: int = DEFAULT_STATS_PORT,
) -> None:
    """Run CONNECT proxy and stats server until cancelled (in-cluster pod entrypoint)."""
    proxy = TunnelProxy(host="0.0.0.0", port=proxy_port)
    await proxy.start()
    stats_server = await _run_stats_server(proxy, "0.0.0.0", stats_port)
    try:
        await asyncio.Event().wait()
    finally:
        stats_server.close()
        await stats_server.wait_closed()
        await proxy.stop()


def main() -> None:
    """CLI entrypoint for the ``e2e-tunnel-proxy`` Kubernetes pod."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_in_cluster())


if __name__ == "__main__":
    main()

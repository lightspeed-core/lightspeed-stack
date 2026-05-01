"""Step definitions for proxy and TLS networking e2e tests.

These tests configure Llama Stack's run.yaml with NetworkConfig settings
(proxy, TLS) and verify the full pipeline works through the Lightspeed Stack.
The proxy sits between Llama Stack and whichever remote LLM provider is active.

Config switching uses the same pattern as other e2e tests: overwrite the
host-mounted run.yaml and restart Docker containers. Restarts are not
triggered from ``The original Llama Stack config is restored if modified``;
list ``Llama Stack is restarted`` / ``Lightspeed Stack is restarted`` in the
feature file so readers see every restart. Cleanup restores the backup file
(and stops proxy servers) before each scenario.
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Optional

import trustme
import yaml
from behave import given, then  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

from tests.e2e.utils.utils import (
    is_prow_environment,
    restart_container,
    wait_for_lightspeed_stack_http_ready,
)

# Llama Stack config — mounted into the container from the host
_LLAMA_STACK_CONFIG = "run.yaml"
_LLAMA_STACK_CONFIG_BACKUP = "run.yaml.proxy-backup"


def _is_docker_mode() -> bool:
    """Check if services are running in Docker containers (local e2e)."""
    if is_prow_environment():
        return False
    result = subprocess.run(
        ["docker", "ps", "--filter", "name=llama-stack", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "llama-stack" in result.stdout


def _host_special_dns_from_container(hostname: str) -> Optional[str]:
    """Resolve a host-gateway hostname inside llama-stack to an IPv4 address.

    Docker exposes ``host.docker.internal`` or ``host.containers.internal``
    for reaching the host. Resolving from inside the container matches the address
    the runtime uses and fixes proxy routing when the bridge gateway IP is wrong.

    Parameters:
    ----------
        hostname: Name to resolve (e.g. ``host.docker.internal``).

    Returns:
    -------
        IPv4 dotted-quad string, or ``None`` if the name does not resolve.
    """
    probe = (
        "import socket,sys\n"
        "try:\n"
        "    print(socket.gethostbyname(sys.argv[1]))\n"
        "except OSError:\n"
        "    raise SystemExit(1)\n"
    )
    result = subprocess.run(
        [
            "docker",
            "exec",
            "llama-stack",
            "python3",
            "-c",
            probe,
            hostname,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if result.returncode != 0:
        return None
    ip = result.stdout.strip()
    return ip or None


def _get_proxy_host(is_docker: bool) -> str:
    """Get the host address that containers can use to reach the proxy on the host.

    Parameters:
    ----------
        is_docker: Whether services are running in Docker (local e2e).
    """
    if not is_docker:
        return "127.0.0.1"
    for hostname in ("host.docker.internal", "host.containers.internal"):
        resolved = _host_special_dns_from_container(hostname)
        if resolved:
            return resolved
    result = subprocess.run(
        [
            "docker",
            "network",
            "inspect",
            "lightspeednet",
            "--format",
            "{{(index .IPAM.Config 0).Gateway}}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    gateway = result.stdout.strip()
    if gateway:
        return gateway
    return "172.17.0.1"


def _load_llama_config() -> dict[str, Any]:
    """Load the base Llama Stack run config."""
    with open(_LLAMA_STACK_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _write_config(config: dict[str, Any], path: str) -> None:
    """Write a YAML config file."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False)


def _find_inference_provider(
    context: Context, config: dict[str, Any]
) -> dict[str, Any]:
    """Find the target remote inference provider in the config.

    Priority:
    1. ``context.default_provider`` (detected in ``before_all``), if present.
    2. First remote inference provider in ``run.yaml``.

    Raises:
        AssertionError: If no suitable remote inference provider is found.
    """
    providers = config.get("providers", {})
    inference_providers = providers.get("inference", [])
    target_provider_id = getattr(context, "default_provider", None)

    if target_provider_id:
        for provider in inference_providers:
            if provider.get("provider_id") == target_provider_id:
                provider_type = str(provider.get("provider_type", ""))
                assert provider_type.startswith("remote::"), (
                    "Configured default provider "
                    f"'{target_provider_id}' is not a remote provider in run.yaml"
                )
                return provider

    for provider in inference_providers:
        provider_type = str(provider.get("provider_type", ""))
        if provider_type.startswith("remote::"):
            return provider

    raise AssertionError(
        "No remote inference provider found in run.yaml "
        "(expected provider_type starting with 'remote::')"
    )


def _backup_llama_config() -> None:
    """Create a backup of the current run.yaml if not already backed up."""
    if not os.path.exists(_LLAMA_STACK_CONFIG_BACKUP):
        shutil.copy(_LLAMA_STACK_CONFIG, _LLAMA_STACK_CONFIG_BACKUP)


# --- Background Steps ---


def _stop_proxy(context: Context, attr: str, loop_attr: str) -> None:
    """Stop a proxy server and its event loop if they exist on the context."""
    proxy = getattr(context, attr, None)
    loop = getattr(context, loop_attr, None)
    if proxy is not None and loop is not None:
        fut = asyncio.run_coroutine_threadsafe(proxy.stop(), loop)
        try:
            fut.result(timeout=30)
        except Exception:
            pass
        loop.call_soon_threadsafe(loop.stop)
        time.sleep(0.5)
    if hasattr(context, attr):
        delattr(context, attr)
    if hasattr(context, loop_attr):
        delattr(context, loop_attr)


@given("The original Llama Stack config is restored if modified")
def restore_if_modified(context: Context) -> None:
    """Restore original run.yaml if a previous scenario modified it.

    Called from Background so every scenario starts with a clean config,
    even if the previous scenario failed mid-way. Also stops any proxy
    servers left running from the previous scenario.
    """
    # Stop any leftover proxy servers from previous scenario
    _stop_proxy(context, "tunnel_proxy", "proxy_loop")
    _stop_proxy(context, "interception_proxy", "interception_proxy_loop")

    if os.path.exists(_LLAMA_STACK_CONFIG_BACKUP):
        print(
            f"Restoring original Llama Stack config from {_LLAMA_STACK_CONFIG_BACKUP}..."
        )
        shutil.move(_LLAMA_STACK_CONFIG_BACKUP, _LLAMA_STACK_CONFIG)


# --- Service Restart Steps ---


@given("Llama Stack is restarted")
def restart_llama_stack(context: Context) -> None:
    """Restart the Llama Stack container."""
    restart_container("llama-stack")


@given("Lightspeed Stack is restarted")
def restart_lightspeed_stack(context: Context) -> None:
    """Restart the Lightspeed Stack container."""
    restart_container("lightspeed-stack")
    wait_for_lightspeed_stack_http_ready()


# --- Tunnel Proxy Steps ---


@given("A tunnel proxy is running on port {port:d}")
def start_tunnel_proxy(context: Context, port: int) -> None:
    """Start a tunnel proxy in a background thread."""
    from tests.e2e.proxy.tunnel_proxy import TunnelProxy

    # Bind to 0.0.0.0 so Docker containers can reach the proxy
    proxy = TunnelProxy(host="0.0.0.0", port=port)
    loop = asyncio.new_event_loop()
    context.proxy_loop = loop
    context.tunnel_proxy = proxy

    def run_proxy() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(proxy.start())
        loop.run_forever()

    thread = threading.Thread(target=run_proxy, daemon=True)
    thread.start()
    time.sleep(1)


@given("Llama Stack is configured to route inference through the tunnel proxy")
def configure_llama_tunnel_proxy(context: Context) -> None:
    """Modify run.yaml with proxy config pointing to the tunnel proxy."""
    _backup_llama_config()
    proxy = context.tunnel_proxy
    proxy_host = _get_proxy_host(context.is_docker_mode)
    config = _load_llama_config()
    provider = _find_inference_provider(context, config)

    if "config" not in provider:
        provider["config"] = {}
    provider["config"]["network"] = {
        "proxy": {
            "url": f"http://{proxy_host}:{proxy.port}",
        }
    }

    _write_config(config, _LLAMA_STACK_CONFIG)


@given('Llama Stack is configured to route inference through proxy "{proxy_url}"')
def configure_llama_unreachable_proxy(context: Context, proxy_url: str) -> None:
    """Modify run.yaml with a proxy URL (may be unreachable)."""
    _backup_llama_config()
    config = _load_llama_config()
    provider = _find_inference_provider(context, config)

    if "config" not in provider:
        provider["config"] = {}
    provider["config"]["network"] = {
        "proxy": {
            "url": proxy_url,
        }
    }

    _write_config(config, _LLAMA_STACK_CONFIG)


# --- Interception Proxy Steps ---


@given("An interception proxy with trustme CA is running on port {port:d}")
def start_interception_proxy(context: Context, port: int) -> None:
    """Start an interception proxy with trustme CA."""
    from tests.e2e.proxy.interception_proxy import InterceptionProxy

    ca = trustme.CA()
    # Bind to 0.0.0.0 so Docker containers can reach the proxy
    proxy = InterceptionProxy(ca=ca, host="0.0.0.0", port=port)

    # Write cert to a known path
    ca_cert_path = Path(tempfile.gettempdir()) / "interception-proxy-ca.pem"
    proxy.export_ca_cert(ca_cert_path)

    # In Docker mode, copy the cert into the llama-stack container
    if context.is_docker_mode:
        container_cert_path = "/tmp/interception-proxy-ca.pem"
        subprocess.run(
            ["docker", "cp", str(ca_cert_path), f"llama-stack:{container_cert_path}"],
            check=True,
        )
        context.ca_cert_path_for_config = container_cert_path
    else:
        context.ca_cert_path_for_config = str(ca_cert_path)

    loop = asyncio.new_event_loop()
    context.interception_proxy_loop = loop
    context.interception_proxy = proxy

    def run_proxy() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(proxy.start())
        loop.run_forever()

    thread = threading.Thread(target=run_proxy, daemon=True)
    thread.start()
    time.sleep(1)


@given(
    "Llama Stack is configured to route inference through "
    "the interception proxy with CA cert"
)
def configure_llama_interception_with_ca(context: Context) -> None:
    """Modify run.yaml with interception proxy and CA cert config."""
    _backup_llama_config()
    proxy = context.interception_proxy
    proxy_host = _get_proxy_host(context.is_docker_mode)
    config = _load_llama_config()
    provider = _find_inference_provider(context, config)

    if "config" not in provider:
        provider["config"] = {}
    provider["config"]["network"] = {
        "proxy": {
            "url": f"http://{proxy_host}:{proxy.port}",
            "cacert": context.ca_cert_path_for_config,
        },
        "tls": {
            "verify": context.ca_cert_path_for_config,
        },
    }

    _write_config(config, _LLAMA_STACK_CONFIG)


@given(
    "Llama Stack is configured to route inference through "
    "the interception proxy without CA cert"
)
def configure_llama_interception_no_ca(context: Context) -> None:
    """Modify run.yaml with interception proxy but NO CA cert."""
    _backup_llama_config()
    proxy = context.interception_proxy
    proxy_host = _get_proxy_host(context.is_docker_mode)
    config = _load_llama_config()
    provider = _find_inference_provider(context, config)

    if "config" not in provider:
        provider["config"] = {}
    provider["config"]["network"] = {
        "proxy": {
            "url": f"http://{proxy_host}:{proxy.port}",
        },
    }

    _write_config(config, _LLAMA_STACK_CONFIG)


# --- TLS Steps ---


@given('Llama Stack is configured with minimum TLS version "{version}"')
def configure_llama_tls_version(context: Context, version: str) -> None:
    """Modify run.yaml with TLS version config."""
    _backup_llama_config()
    config = _load_llama_config()
    provider = _find_inference_provider(context, config)

    if "config" not in provider:
        provider["config"] = {}
    provider["config"]["network"] = {
        "tls": {
            "min_version": version,
        }
    }

    _write_config(config, _LLAMA_STACK_CONFIG)


@given('Llama Stack is configured with ciphers "{ciphers}"')
def configure_llama_ciphers(context: Context, ciphers: str) -> None:
    """Modify run.yaml with cipher suite config."""
    _backup_llama_config()
    config = _load_llama_config()
    provider = _find_inference_provider(context, config)

    if "config" not in provider:
        provider["config"] = {}
    provider["config"]["network"] = {
        "tls": {
            "ciphers": ciphers.split(":"),
        }
    }

    _write_config(config, _LLAMA_STACK_CONFIG)


# --- Proxy Verification Steps ---


@then(
    "The tunnel proxy handled at least {count:d} " "CONNECT request to the LLM provider"
)
def verify_tunnel_proxy_used(context: Context, count: int) -> None:
    """Verify the tunnel proxy received CONNECT requests."""
    proxy = context.tunnel_proxy
    assert proxy.connect_count >= count, (
        f"Expected at least {count} CONNECT requests, " f"got {proxy.connect_count}"
    )
    assert proxy.last_connect_target is not None, "No CONNECT target recorded"


@then("The interception proxy intercepted at least {count:d} connection")
def verify_interception_proxy_used(context: Context, count: int) -> None:
    """Verify the interception proxy intercepted connections."""
    proxy = context.interception_proxy
    assert proxy.connect_count >= count, (
        f"Expected at least {count} intercepted connections, "
        f"got {proxy.connect_count}"
    )

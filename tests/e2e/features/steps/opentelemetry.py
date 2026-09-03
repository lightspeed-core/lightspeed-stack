"""Step definitions for the OpenTelemetry telemetry-delivery E2E scenario.

These steps bring up a mock OTLP/HTTP collector (the ``mock-otel`` Docker
Compose service), reconfigure the Lightspeed Core Stack to export spans/events
to it, and assert that telemetry containing a scenario marker is delivered.

The Lightspeed Core Stack has no in-app tracing configuration: the OTEL SDK is
enabled only when the container entrypoint launches the app under
``opentelemetry-instrument``, which happens when ``OTEL_SDK_DISABLED=false``.
The exporter target is then read from the standard ``OTEL_*`` environment
variables. Because those are set at container-creation time, the
"configure to export" step recreates the container rather than restarting it.
"""

import os
import subprocess
import time

import requests
from behave import given, then  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

from tests.e2e.utils.utils import (
    absolute_repo_path,
    is_prow_environment,
    wait_for_container_health,
    wait_for_lightspeed_stack_http_ready,
)

# Compose service / container name for the mock collector (see docker-compose*.yaml).
MOCK_OTEL_SERVICE = "mock-otel"
LIGHTSPEED_STACK_SERVICE = "lightspeed-stack"

# Endpoint the Lightspeed Core Stack exports to, on the shared compose network.
# Overridable so the scenario can target an external collector if needed.
OTEL_EXPORT_ENDPOINT = os.getenv(
    "E2E_OTEL_EXPORT_ENDPOINT", f"http://{MOCK_OTEL_SERVICE}:4318"
)
OTEL_EXPORT_PROTOCOL = "http/protobuf"
OTEL_EXPORT_SERVICE_NAME = os.getenv("E2E_OTEL_SERVICE_NAME", "lightspeed-stack-e2e")

# Host-side control API of the mock collector (published port from docker-compose).
_MOCK_OTEL_HOST = os.getenv("E2E_OTEL_MOCK_HOST", "localhost")
_MOCK_OTEL_PORT = os.getenv("E2E_OTEL_MOCK_PORT", "4318")
MOCK_OTEL_CONTROL_BASE = f"http://{_MOCK_OTEL_HOST}:{_MOCK_OTEL_PORT}"

# Delivery is asynchronous: the SDK batches spans before export. Poll generously.
_DELIVERY_TIMEOUT_S = float(os.getenv("E2E_OTEL_DELIVERY_TIMEOUT_S", "45"))
_DELIVERY_POLL_INTERVAL_S = 2.0
_HEALTH_TIMEOUT_S = 30.0


def _compose_file(context: Context) -> str:
    """Return the absolute path to the Compose file for the active deployment mode."""
    name = (
        "docker-compose-library.yaml"
        if getattr(context, "is_library_mode", False)
        else "docker-compose.yaml"
    )
    return absolute_repo_path(name)


def _compose(context: Context, *args: str, timeout: int = 300) -> None:
    """Run ``docker compose -f <file> <args>`` from the repo root, raising on failure."""
    cmd = ["docker", "compose", "-f", _compose_file(context), *args]
    result = subprocess.run(
        cmd,
        cwd=absolute_repo_path("."),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        print(result.stderr, end="")
        raise AssertionError(f"`{' '.join(cmd)}` failed with code {result.returncode}")


def _skip_if_prow(context: Context) -> bool:
    """Skip the scenario when running on Prow, where compose is unavailable.

    The OTEL scenario relies on Docker Compose and the mock ``mock-otel``
    collector, which are not deployed on Prow/OpenShift. Returns True when the
    scenario was skipped so the caller can return early.
    """
    if is_prow_environment():
        context.scenario.skip(
            "OpenTelemetry delivery scenario requires Docker Compose and the "
            "mock OTEL collector, which are not deployed on Prow/OpenShift."
        )
        return True
    return False


def _wait_for_mock_health() -> None:
    """Poll the mock collector control API until it reports healthy."""
    url = f"{MOCK_OTEL_CONTROL_BASE}/health"
    deadline = time.monotonic() + _HEALTH_TIMEOUT_S
    last_error = "no response"
    while time.monotonic() < deadline:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last_error = f"{exc.__class__.__name__}: {exc}"
        time.sleep(1.0)
    raise AssertionError(
        f"Mock OTEL collector did not become healthy at {url!r} "
        f"within {_HEALTH_TIMEOUT_S:.0f}s (last: {last_error})"
    )


def _reset_mock_collector() -> None:
    """Clear any telemetry buffered by the mock collector from prior runs."""
    response = requests.post(f"{MOCK_OTEL_CONTROL_BASE}/reset", timeout=5)
    assert (
        response.status_code == 200
    ), f"Failed to reset mock OTEL collector: HTTP {response.status_code}"


def _poll_collector_contains(marker: str) -> bool:
    """Return True once the collector has buffered a payload containing ``marker``."""
    url = f"{MOCK_OTEL_CONTROL_BASE}/received"
    deadline = time.monotonic() + _DELIVERY_TIMEOUT_S
    while True:
        try:
            response = requests.get(url, params={"contains": marker}, timeout=5)
            if response.status_code == 200 and response.json().get("found"):
                return True
        except requests.RequestException:
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(_DELIVERY_POLL_INTERVAL_S)


@given("An OpenTelemetry service is running and listening for OTLP data")
def otel_service_running(context: Context) -> None:
    """Build and start the mock OTLP collector, then clear its buffer.

    Brings up the ``mock-otel`` Compose service on the shared network, waits for
    it to report healthy (Docker health and its own control API), and resets any
    previously buffered telemetry so the scenario starts from a clean slate.
    """
    if _skip_if_prow(context):
        return
    _compose(context, "up", "-d", "--build", MOCK_OTEL_SERVICE)
    wait_for_container_health(MOCK_OTEL_SERVICE)
    _wait_for_mock_health()
    _reset_mock_collector()
    context.otel_collector_endpoint = OTEL_EXPORT_ENDPOINT


@given("The service is configured to export data to the OpenTelemetry service")
def configure_service_export(context: Context) -> None:
    """Enable OTEL export and recreate the service so the exporter is active.

    The OTEL SDK is only initialized when the entrypoint launches the app under
    ``opentelemetry-instrument`` (``OTEL_SDK_DISABLED=false``), and the exporter
    target comes from environment variables fixed at container creation. This
    sets those variables and force-recreates the ``lightspeed-stack`` container
    so it exports HTTP/protobuf to the mock collector.
    """
    if _skip_if_prow(context):
        return
    os.environ["OTEL_SDK_DISABLED"] = "false"
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = OTEL_EXPORT_ENDPOINT
    os.environ["OTEL_EXPORTER_OTLP_PROTOCOL"] = OTEL_EXPORT_PROTOCOL
    os.environ["OTEL_SERVICE_NAME"] = OTEL_EXPORT_SERVICE_NAME
    # before_all sets OTEL_ANONYMIZATION_SECRET; keep any existing value.
    os.environ.setdefault(
        "OTEL_ANONYMIZATION_SECRET", "e2e-test-secret-do-not-use-in-production"
    )

    _compose(
        context,
        "up",
        "-d",
        "--force-recreate",
        "--no-deps",
        LIGHTSPEED_STACK_SERVICE,
    )
    wait_for_container_health(LIGHTSPEED_STACK_SERVICE)
    wait_for_lightspeed_stack_http_ready()
    context.otel_export_configured = True


@then("The service exported an OpenTelemetry event containing {marker}")
def service_exported_event(context: Context, marker: str) -> None:
    """Assert the service emitted telemetry containing ``marker`` to the collector.

    Polls the mock collector until a buffered OTLP payload contains the marker,
    confirming the export path from the Lightspeed Core Stack is working.
    """
    assert getattr(
        context, "otel_collector_endpoint", None
    ), "The OpenTelemetry service must be started before asserting on exports"
    marker = marker.strip()
    assert _poll_collector_contains(marker), (
        f"No exported OpenTelemetry data containing {marker!r} reached the mock "
        f"collector within {_DELIVERY_TIMEOUT_S:.0f}s"
    )


@then("The OpenTelemetry service received data containing {marker}")
def collector_received_data(context: Context, marker: str) -> None:
    """Assert the mock collector buffered telemetry containing ``marker``.

    Verifies delivery from the collector's perspective; polls to tolerate the
    SDK's batched, asynchronous export.
    """
    assert getattr(
        context, "otel_collector_endpoint", None
    ), "The OpenTelemetry service must be started before asserting on delivery"
    marker = marker.strip()
    assert _poll_collector_contains(marker), (
        f"Mock OTEL collector did not receive data containing {marker!r} "
        f"within {_DELIVERY_TIMEOUT_S:.0f}s"
    )

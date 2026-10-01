"""Step definitions for the OpenTelemetry telemetry-delivery E2E scenario.

The Lightspeed Core Stack exports spans/events to the mock OTLP/HTTP collector
(the ``mock-otel`` Docker Compose service) from startup: the ``OTEL_*``
environment variables that enable ``opentelemetry-instrument`` and point the
exporter at the collector are baked into the Compose files, so no per-scenario
reconfiguration is needed. These steps only reset the collector's buffer at the
start of the scenario and assert that telemetry containing a scenario marker is
delivered.
"""

import os
import time

import requests
from behave import given, then  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

from tests.e2e.utils.utils import wait_for_container_health

# Compose service / container name for the mock collector (see docker-compose*.yaml).
MOCK_OTEL_SERVICE = "mock-otel"

# Host-side control API of the mock collector (published port from docker-compose).
_MOCK_OTEL_HOST = os.getenv("E2E_OTEL_MOCK_HOST", "localhost")
_MOCK_OTEL_PORT = os.getenv("E2E_OTEL_MOCK_PORT", "4318")
MOCK_OTEL_CONTROL_BASE = f"http://{_MOCK_OTEL_HOST}:{_MOCK_OTEL_PORT}"

# Delivery is asynchronous: the SDK batches spans before export. Poll generously.
_DELIVERY_TIMEOUT_S = float(os.getenv("E2E_OTEL_DELIVERY_TIMEOUT_S", "45"))
_DELIVERY_POLL_INTERVAL_S = 2.0


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
    while time.monotonic() < deadline:
        try:
            response = requests.get(url, params={"contains": marker}, timeout=5)
            if response.status_code == 200 and response.json().get("found"):
                return True
        except requests.RequestException:
            pass
        time.sleep(_DELIVERY_POLL_INTERVAL_S)
    return False


@given("An OpenTelemetry service is running and listening for OTLP data")
def otel_service_running(context: Context) -> None:
    """Wait for the mock OTLP collector to be healthy and clear its buffer.

    The ``mock-otel`` Compose service starts with the rest of the stack and its
    readiness is enforced by the Compose healthcheck, so this step waits for
    that health status and resets any previously buffered telemetry so the
    scenario starts from a clean slate. The Lightspeed Core Stack already
    exports to the collector via the ``OTEL_*`` variables set in the Compose
    files.
    """
    wait_for_container_health(MOCK_OTEL_SERVICE)
    _reset_mock_collector()
    context.otel_collector_ready = True


@then("The OpenTelemetry service received data containing {marker}")
def collector_received_data(context: Context, marker: str) -> None:
    """Assert the mock collector buffered telemetry containing ``marker``.

    Verifies delivery from the collector's perspective; polls to tolerate the
    SDK's batched, asynchronous export.
    """
    assert getattr(
        context, "otel_collector_ready", False
    ), "The OpenTelemetry service must be started before asserting on delivery"
    marker = marker.strip()
    assert _poll_collector_contains(marker), (
        f"Mock OTEL collector did not receive data containing {marker!r} "
        f"within {_DELIVERY_TIMEOUT_S:.0f}s"
    )

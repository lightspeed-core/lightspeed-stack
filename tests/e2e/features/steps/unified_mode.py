"""Step definitions for the unified-mode e2e features (LCORE-2343).

Only the startup-log evidence step lives here. Everything else the five
``unified-mode-*.feature`` files need — applying a configuration, restarting
containers, hitting ``readiness`` and ``query`` — resolves through the generic
steps, and the configuration validation, migration and synthesis assertions
moved to ``tests/integration/`` (``test_unified_mode_cli.py``,
``test_unified_synthesis.py``): e2e steps observe the deployed stack from
outside and never import from or execute anything under ``src/``. See
``docs/testing/e2e_testing.md``, "Choosing the Test Layer".

The log step is mode-aware: in server mode the synthesis evidence is emitted by
the ogx container (entrypoint + config CLI), not the lightspeed-stack
container the Gherkin names; the scenario's intent (R10: the synthesized path
is logged at startup) is asserted against the container that actually
synthesizes.
"""

import re
import subprocess

from behave import then  # pyright: ignore
from behave.runner import Context


def _container_started_at(container: str) -> str:
    """Return the container's last start timestamp (RFC 3339) from ``docker inspect``."""
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.StartedAt}}", container],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert (
        result.returncode == 0
    ), f"docker inspect {container} failed: {result.stderr[-500:]}"
    started_at = result.stdout.strip()
    assert started_at, f"docker inspect {container} returned no StartedAt"
    return started_at


@then("the lightspeed-stack container logs contain synthesized run.yaml")
def container_logs_show_synthesis(context: Context) -> None:
    """Assert the container that synthesizes logged the synthesized-config path.

    Library mode: the lightspeed-stack container itself synthesizes in-process
    and logs "Using synthesized OGX config at <path>". Server mode: synthesis
    happens in the ogx container (entrypoint + config CLI), which
    echoes the generated-config path — the Gherkin names lightspeed-stack, but
    the scenario's intent (R10: the path is logged at startup) can only be
    observed on the synthesizing container. Deviation agreed in planning (Q2).

    ``docker logs`` accumulates across ``docker restart``, and the CI baseline
    configurations already synthesize (library) or generate (server) on the
    very first compose boot — so an unscoped read would pass on evidence from
    an earlier boot. The read is therefore limited to lines since the
    container's current ``StartedAt``, i.e. the restart the scenario just
    performed under the unified fixture.

    The pattern must carry a path and must be unique to synthesis. The
    entrypoint's own lines cannot provide that: it echoes "(mode
    auto-detected)" before generation runs and unconditionally, and it echoes
    "Using generated config: <path>" identically for the synthesis and the
    legacy-enrichment branch (scripts/ogx-entrypoint.sh). Matching either
    would let the scenario pass when the unified fixture never reached the
    container and the entrypoint enriched a run.yaml instead — which is the
    one thing this scenario exists to rule out. The fallback line "Using
    original config:" does not discriminate either; it is printed only when
    generation *failed*, so it is absent from a successful enrichment too.

    So both modes match a line that only the synthesis path writes:
    src/client/ogx.py in library mode, src/ogx_configuration.py in server
    mode. The latter reaches the container log only because main() configures
    logging — as a bare script nothing installs a root handler and
    logging.lastResort drops everything below WARNING.
    """
    if context.is_library_mode:
        container = "lightspeed-stack"
        pattern = r"Using synthesized OGX config at \S+"
    else:
        container = "ogx"
        pattern = r"Wrote synthesized OGX configuration to \S+"

    started_at = _container_started_at(container)
    result = subprocess.run(
        ["docker", "logs", "--since", started_at, container],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert (
        result.returncode == 0
    ), f"docker logs {container} failed: {result.stderr[-500:]}"
    logs = result.stdout + result.stderr
    # Checked before the pattern assert: when the entrypoint genuinely fell
    # back, the pattern is absent too, and this is the message that says why.
    if not context.is_library_mode:
        assert "Using original config:" not in logs, (
            f"{container} fell back to the original run.yaml on this boot; "
            "the unified fixture was not synthesized"
        )
    assert re.search(pattern, logs), (
        f"{container} logs since {started_at} carry no synthesis-path evidence "
        f"(pattern {pattern!r} not found)"
    )

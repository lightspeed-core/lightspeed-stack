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
the llama-stack container (entrypoint + config CLI), not the lightspeed-stack
container the Gherkin names; the scenario's intent (R10: the synthesized path
is logged at startup) is asserted against the container that actually
synthesizes.
"""

import re
import subprocess

from behave import then  # pyright: ignore
from behave.runner import Context


@then("the lightspeed-stack container logs contain synthesized run.yaml")
def container_logs_show_synthesis(context: Context) -> None:
    """Assert the container that synthesizes logged the synthesized-config path.

    Library mode: the lightspeed-stack container itself synthesizes in-process
    and logs "Using synthesized OGX config at <path>". Server mode: synthesis
    happens in the llama-stack container (entrypoint + config CLI), which logs
    the generated-config path — the Gherkin names lightspeed-stack, but the
    scenario's intent (R10: the path is logged at startup) can only be observed
    on the synthesizing container. Deviation agreed in planning (Q2).

    Every accepted pattern must carry a path. The entrypoint echoes "(mode
    auto-detected)" *before* synthesis runs and unconditionally, so matching it
    would let the scenario pass on a failed synthesis — the opposite of what
    R10 asks. "Using generated config: <path>" is only echoed on success.
    """
    if context.is_library_mode:
        container = "lightspeed-stack"
        pattern = r"Using synthesized OGX config at \S+"
    else:
        container = "llama-stack"
        pattern = (
            r"Wrote synthesized OGX configuration to \S+"
            r"|Using generated config:\s*\S+"
        )

    result = subprocess.run(
        ["docker", "logs", container],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert (
        result.returncode == 0
    ), f"docker logs {container} failed: {result.stderr[-500:]}"
    logs = result.stdout + result.stderr
    assert re.search(pattern, logs), (
        f"{container} logs carry no synthesis-path evidence "
        f"(pattern {pattern!r} not found)"
    )

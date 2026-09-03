"""Implementation of common test steps."""

import subprocess
import time

from behave import given  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

from tests.e2e.utils.utils import is_prow_environment

# Behave may clear user attributes on ``context`` between scenarios; keep this
# in module scope so "disrupt once per feature" survives per-scenario resets.
# Mutate one dict entry so we need not reassign a module-level bool (no global).
_llama_stack_disrupt_once: dict[str, bool] = {"applied": False}

# Behave clears user attributes on ``context`` between scenarios; store
# ``was_running`` at module level so ``after_feature`` can still see it.
_ogx_was_running: dict[str, bool] = {"value": False}


def get_ogx_was_running() -> bool:
    """Return whether OGX was running before the disruption step."""
    return _ogx_was_running["value"]


def reset_ogx_was_running() -> None:
    """Clear the module-level was_running flag after restoration."""
    _ogx_was_running["value"] = False


def reset_llama_stack_disrupt_once_tracking() -> None:
    """Reset before each feature; see ``environment.before_feature``."""
    _llama_stack_disrupt_once["applied"] = False
    _ogx_was_running["value"] = False


def _force_lightspeed_restart_after_llama_disrupt(context: Context) -> None:
    """Do not skip the next Lightspeed restart after OGX is disrupted."""
    context.force_lightspeed_restart_after_mcp_config_reset = True
    context.lightspeed_stack_skip_restart = False


def _force_lightspeed_restart_after_llama_disrupt(context: Context) -> None:
    """Do not skip the next Lightspeed restart after Llama is disrupted."""
    context.force_lightspeed_restart_after_mcp_config_reset = True
    context.lightspeed_stack_skip_restart = False


@given("The llama-stack connection is disrupted")
def llama_stack_connection_broken(context: Context) -> None:
    """Break llama_stack connection by stopping the container.

    Disrupts the OGX service by stopping its Docker container and
    records whether it was running.

    The real disruption runs only once per feature until OGX is running again:
    the first invocation performs Docker/Prow disruption; later invocations no-op.
    ``reset_llama_stack_disrupt_once_tracking`` clears the skip flag from
    ``before_feature`` and after OGX is restored (``restart_container``,
    ``_restore_llama_stack``) so the next disrupt step stops the container again.
    Tracking uses module state (not ``context`` alone) because Behave can clear
    custom attributes on ``context`` between scenarios.

    Checks whether the Docker container named "llama-stack" is running; if it
    is, stops the container, waits briefly for the disruption to take effect,
    and sets `context.ogx_was_running` to True so callers can restore
    state later. If the container is not running, the flag remains False. On
    failure to run Docker commands, prints a warning message describing the
    error.

    Parameters:
    ----------
        context (behave.runner.Context): Behave context used to store
        `ogx_was_running` and share state between steps.
    """
    if _llama_stack_disrupt_once["applied"]:
        print("OGX disruption skipped (already applied once this feature)")
        _force_lightspeed_restart_after_llama_disrupt(context)
        return

    # Store original state for restoration (only on the real disruption path).
    # Write to both context (backward compat) and module-level dict (survives
    # Behave's per-scenario context clearing).
    context.ogx_was_running = False
    _ogx_was_running["value"] = False

    if is_prow_environment():
        from tests.e2e.utils.prow_utils import disrupt_llama_stack_pod

        was_running = disrupt_llama_stack_pod()
        context.ogx_was_running = was_running
        _ogx_was_running["value"] = was_running
        _llama_stack_disrupt_once["applied"] = True
        _force_lightspeed_restart_after_llama_disrupt(context)
        return

    # Docker-based disruption
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", "llama-stack"],
            capture_output=True,
            text=True,
            check=True,
        )

        if result.stdout.strip():
            context.ogx_was_running = True
            _ogx_was_running["value"] = True
            subprocess.run(
                ["docker", "stop", "llama-stack"], check=True, capture_output=True
            )

            # Wait a moment for the connection to be fully disrupted
            time.sleep(2)

            print("OGX connection disrupted successfully")
        else:
            print("OGX container was not running")

    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not disrupt OGX connection: {e}")
        return

    _llama_stack_disrupt_once["applied"] = True
    _force_lightspeed_restart_after_llama_disrupt(context)

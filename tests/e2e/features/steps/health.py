"""Implementation of common test steps."""

import subprocess
import time
from behave import given  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context

from tests.e2e.utils.utils import is_prow_environment


@given("The llama-stack connection is disrupted")
def llama_stack_connection_broken(context: Context) -> None:
    """Break llama_stack connection by stopping the container.

    Disrupts the Llama Stack service by stopping its Docker container and
    records whether it was running.

    Checks whether the Docker container named "llama-stack" is running; if it
    is, stops the container, waits briefly for the disruption to take effect,
    and sets `context.llama_stack_was_running` to True so callers can restore
    state later. If the container is not running, the flag remains False. On
    failure to run Docker commands, prints a warning message describing the
    error.

    Parameters:
        context (behave.runner.Context): Behave context used to store
        `llama_stack_was_running` and share state between steps.
    """
    # Store original state for restoration
    context.llama_stack_was_running = False

    if is_prow_environment():
        from tests.e2e.utils.prow_utils import disrupt_llama_stack_pod

        context.llama_stack_was_running = disrupt_llama_stack_pod()
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
            context.llama_stack_was_running = True
            subprocess.run(
                ["docker", "stop", "llama-stack"], check=True, capture_output=True
            )

            # Wait a moment for the connection to be fully disrupted
            time.sleep(2)

            print("Llama Stack connection disrupted successfully")
        else:
            print("Llama Stack container was not running")

    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not disrupt Llama Stack connection: {e}")


@given("the service is stopped")
def stop_service(context: Context) -> None:
    """Stop service.

    Stop a service used by the current test scenario.

    Parameters:
        context (Context): Behave step context carrying scenario state and configuration.
    """
    # TODO: add step implementation
    assert context is not None

"""Implementation of common test steps."""

import subprocess
import time
from behave import given  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context


@given("The llama-stack connection is disrupted")
def llama_stack_connection_broken(context: Context) -> None:
    """Break llama_stack connection by stopping the container."""
    # Store original state for restoration
    context.llama_stack_was_running = False

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
    """Stop service."""
    # TODO: add step implementation
    assert context is not None

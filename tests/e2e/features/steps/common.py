"""Implementation of common test steps."""

from behave import given  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context
import os


@given("The service is started locally")
def service_is_started_locally(context: Context) -> None:
    """Check the service status.

    Populate the Behave context with local service endpoint values read from
    environment variables.

    Parameters:
        context (Context): Behave context object to receive the endpoint attributes.
    """
    assert context is not None
    context.hostname = os.getenv("E2E_LSC_HOSTNAME", "localhost")
    context.port = os.getenv("E2E_LSC_PORT", "8080")
    context.hostname_llama = os.getenv("E2E_LLAMA_HOSTNAME", "localhost")
    context.port_llama = os.getenv("E2E_LLAMA_PORT", "8321")


@given("The system is in default state")
def system_in_default_state(context: Context) -> None:
    """Check the default system state.

    Ensure the Behave test context is present for steps that assume the system
    is in its default state.

    Note: Does NOT clear auth headers, as those may be set in Background section
    and should persist for the entire scenario. Auth headers are explicitly
    cleared by the after_scenario hook in environment.py between scenarios.

    Parameters:
        context (Context): Behave Context instance used to store and share test state.

    Raises:
        AssertionError: If `context` is None.
    """
    assert context is not None
    # Reset MCP error expectation flag for test isolation
    if hasattr(context, "expect_tool_errors"):
        context.expect_tool_errors = False

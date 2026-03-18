"""Implementation of place holder test steps."""

from behave import given  # pyright: ignore[reportAttributeAccessIssue]
from behave.runner import Context


@given('The mcp-file mcp server Authorization header is set to "{header_value}"')
def place_holder_set_mcp_server_header(context: Context, header_value: str) -> None:
    """Set a custom Authorization header value.

    Parameters:
        mcp_server (str): The name of the MCP server.
        header_name (str): The name of the header to set.
        header_value (str): The value to set for the header.
    """
    pass

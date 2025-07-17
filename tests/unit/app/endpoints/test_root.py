"""Unit tests for the / endpoint handler."""

from app.endpoints.root import root_endpoint_handler


def test_root_endpoint():
    """Test the root endpoint handler."""
    request = None
    response = root_endpoint_handler(request)
    assert response is not None

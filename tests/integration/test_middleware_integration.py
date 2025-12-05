"""Integration tests for the global exception middleware."""

from fastapi import Request, status
from fastapi.testclient import TestClient

from configuration import configuration
from models.responses import InternalServerErrorResponse


class TestGlobalExceptionMiddlewareIntegration:  # pylint: disable=too-few-public-methods
    """Integration test suite for global exception middleware."""

    def test_middleware_catches_unexpected_exception_in_endpoint(self) -> None:
        """Test that middleware catches unexpected exceptions from endpoints."""
        configuration_filename = "tests/configuration/lightspeed-stack-proper-name.yaml"
        cfg = configuration
        cfg.load_configuration(configuration_filename)
        from app.main import app  # pylint: disable=C0415

        @app.get("/test-middleware-exception", include_in_schema=False)
        async def _(request: Request) -> dict[str, str]:
            """Test endpoint that raises an unexpected exception for middleware testing."""
            raise ValueError("Unexpected error in endpoint for testing middleware")

        client = TestClient(app)
        response = client.get("/test-middleware-exception")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        response_data = response.json()
        assert "detail" in response_data
        detail = response_data["detail"]
        expected_response = InternalServerErrorResponse.generic()
        expected_detail = expected_response.model_dump()["detail"]
        assert detail["response"] == expected_detail["response"]
        assert detail["cause"] == expected_detail["cause"]

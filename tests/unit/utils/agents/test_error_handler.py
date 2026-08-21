"""Tests for agent inference error mapping."""

from pydantic_ai.exceptions import ModelHTTPError

from models.api.responses.error import (
    InternalServerErrorResponse,
    QuotaExceededResponse,
)
from utils.agents.error_handler import map_pydantic_agent_run_error


class TestMapPydanticAgentRunError:
    """Tests for map_pydantic_agent_run_error with RESOURCE_EXHAUSTED workaround."""

    def test_vertex_429_wrapped_as_500_model_http_error(self) -> None:
        """Test that ModelHTTPError 500 with RESOURCE_EXHAUSTED is treated as 429."""
        exc = ModelHTTPError(
            status_code=500,
            model_name="vertexai/gemini-2.5-flash",
            body="RESOURCE_EXHAUSTED: Quota exceeded for model",
        )
        result = map_pydantic_agent_run_error(exc, "vertexai/gemini-2.5-flash")
        assert isinstance(result, QuotaExceededResponse)

    def test_generic_500_model_http_error(self) -> None:
        """Test that a generic 500 without RESOURCE_EXHAUSTED stays as 500."""
        exc = ModelHTTPError(
            status_code=500,
            model_name="vertexai/gemini-2.5-flash",
            body="Internal server error",
        )
        result = map_pydantic_agent_run_error(exc, "vertexai/gemini-2.5-flash")
        assert isinstance(result, InternalServerErrorResponse)

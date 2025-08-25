"""Unit tests for the /metrics REST API endpoint."""

import pytest
from fastapi import Request

from app.endpoints.metrics import metrics_endpoint_handler
from tests.unit.utils.auth_helpers import mock_authorization_resolvers


@pytest.mark.asyncio
async def test_metrics_endpoint(mocker):
    """Test the metrics endpoint handler."""
    mock_authorization_resolvers(mocker)

    mock_setup_metrics = mocker.patch(
        "app.endpoints.metrics.setup_model_metrics", return_value=None
    )
    request = Request(
        scope={
            "type": "http",
        }
    )
    auth = ("test_user", "token", {})
    response = await metrics_endpoint_handler(auth=auth, request=request)
    assert response is not None
    assert response.status_code == 200
    assert "text/plain" in response.headers["Content-Type"]

    response_body = response.body.decode()

    # Assert metrics were set up
    mock_setup_metrics.assert_called_once()
    # Check if the response contains Prometheus metrics format
    assert "# TYPE ls_rest_api_calls_total counter" in response_body
    assert "# TYPE ls_response_duration_seconds histogram" in response_body
    assert "# TYPE ls_provider_model_configuration gauge" in response_body
    assert "# TYPE ls_llm_calls_total counter" in response_body
    assert "# TYPE ls_llm_calls_failures_total counter" in response_body
    assert "# TYPE ls_llm_calls_failures_created gauge" in response_body
    assert "# TYPE ls_llm_validation_errors_total counter" in response_body
    assert "# TYPE ls_llm_validation_errors_created gauge" in response_body
    assert "# TYPE ls_llm_token_sent_total counter" in response_body
    assert "# TYPE ls_llm_token_received_total counter" in response_body

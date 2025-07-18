"""Unit tests for the /metrics REST API endpoint."""

from app.endpoints.metrics import metrics_endpoint_handler


def test_metrics_endpoint():
    """Test the metrics endpoint handler."""
    response = metrics_endpoint_handler(None)
    assert response is not None
    assert response.status_code == 200
    assert "text/plain" in response.headers["Content-Type"]

    response_body = response.body.decode()

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

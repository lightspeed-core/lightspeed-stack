"""Unit tests for Prometheus metric recording helpers."""

from pytest_mock import MockerFixture

from metrics import recording


def test_measure_response_duration_records_timer(mocker: MockerFixture) -> None:
    """Test that response duration measurement uses the path label timer."""
    mock_timer = mocker.MagicMock()
    mock_metric = mocker.patch("metrics.recording.metrics.response_duration_seconds")
    mock_metric.labels.return_value.time.return_value = mock_timer

    with recording.measure_response_duration("/v1/infer"):
        pass

    mock_metric.labels.assert_called_once_with("/v1/infer")
    mock_metric.labels.return_value.time.assert_called_once()
    mock_timer.__enter__.assert_called_once()
    mock_timer.__exit__.assert_called_once()


def test_measure_response_duration_logs_metric_errors(mocker: MockerFixture) -> None:
    """Test that response duration metric errors are logged and request still proceeds."""
    mock_metric = mocker.patch("metrics.recording.metrics.response_duration_seconds")
    mock_metric.labels.return_value.time.side_effect = AttributeError("missing")
    mock_logger = mocker.patch("metrics.recording.logger")

    with recording.measure_response_duration("/v1/infer"):
        pass

    mock_logger.warning.assert_called_once_with(
        "Failed to start response duration metric", exc_info=True
    )


def test_record_rest_api_call_records_counter(mocker: MockerFixture) -> None:
    """Test that REST API call recording increments the labeled counter."""
    mock_metric = mocker.patch("metrics.recording.metrics.rest_api_calls_total")

    recording.record_rest_api_call("/v1/infer", 200)

    mock_metric.labels.assert_called_once_with("/v1/infer", 200)
    mock_metric.labels.return_value.inc.assert_called_once()


def test_record_rest_api_call_logs_metric_errors(mocker: MockerFixture) -> None:
    """Test that REST API call metric errors are logged and swallowed."""
    mock_metric = mocker.patch("metrics.recording.metrics.rest_api_calls_total")
    mock_metric.labels.return_value.inc.side_effect = AttributeError("missing")
    mock_logger = mocker.patch("metrics.recording.logger")

    recording.record_rest_api_call("/v1/infer", 200)

    mock_logger.warning.assert_called_once_with(
        "Failed to update REST API call metric", exc_info=True
    )


def test_record_llm_call_records_counter(mocker: MockerFixture) -> None:
    """Test that LLM call recording increments the provider/model counter."""
    mock_metric = mocker.patch("metrics.recording.metrics.llm_calls_total")

    recording.record_llm_call("provider1", "model1", "/test-endpoint")

    mock_metric.labels.assert_called_once_with("provider1", "model1", "/test-endpoint")
    mock_metric.labels.return_value.inc.assert_called_once()


def test_record_llm_call_logs_metric_errors(mocker: MockerFixture) -> None:
    """Test that LLM call metric errors are logged and swallowed."""
    mock_metric = mocker.patch("metrics.recording.metrics.llm_calls_total")
    mock_metric.labels.return_value.inc.side_effect = AttributeError("missing")
    mock_logger = mocker.patch("metrics.recording.logger")

    recording.record_llm_call("provider1", "model1", "/test-endpoint")

    mock_logger.warning.assert_called_once_with(
        "Failed to update LLM call metric", exc_info=True
    )


def test_record_llm_failure_records_counter(mocker: MockerFixture) -> None:
    """Test that LLM failure recording increments the provider/model counter."""
    mock_metric = mocker.patch("metrics.recording.metrics.llm_calls_failures_total")

    recording.record_llm_failure("provider1", "model1", "/test-endpoint")

    mock_metric.labels.assert_called_once_with("provider1", "model1", "/test-endpoint")
    mock_metric.labels.return_value.inc.assert_called_once()


def test_record_llm_failure_logs_metric_errors(mocker: MockerFixture) -> None:
    """Test that LLM failure metric errors are logged and swallowed."""
    mock_metric = mocker.patch("metrics.recording.metrics.llm_calls_failures_total")
    mock_metric.labels.return_value.inc.side_effect = TypeError("bad")
    mock_logger = mocker.patch("metrics.recording.logger")

    recording.record_llm_failure("provider1", "model1", "/test-endpoint")

    mock_logger.warning.assert_called_once_with(
        "Failed to update LLM failure metric", exc_info=True
    )


def test_record_llm_validation_error_records_counter(mocker: MockerFixture) -> None:
    """Test that validation error recording increments the counter."""
    mock_metric = mocker.patch(
        "metrics.recording.metrics.llm_calls_validation_errors_total"
    )

    recording.record_llm_validation_error("/test-endpoint")

    mock_metric.labels.assert_called_once_with("/test-endpoint")
    mock_metric.labels.return_value.inc.assert_called_once()


def test_record_llm_validation_error_logs_metric_errors(
    mocker: MockerFixture,
) -> None:
    """Test that validation error metric failures are logged and swallowed."""
    mock_metric = mocker.patch(
        "metrics.recording.metrics.llm_calls_validation_errors_total"
    )
    mock_metric.labels.return_value.inc.side_effect = ValueError("bad")
    mock_logger = mocker.patch("metrics.recording.logger")

    recording.record_llm_validation_error("/test-endpoint")

    mock_logger.warning.assert_called_once_with(
        "Failed to update LLM validation error metric", exc_info=True
    )


def test_record_llm_token_usage_records_counters(mocker: MockerFixture) -> None:
    """Test that token usage recording increments sent and received counters."""
    mock_sent = mocker.patch("metrics.recording.metrics.llm_token_sent_total")
    mock_received = mocker.patch("metrics.recording.metrics.llm_token_received_total")

    recording.record_llm_token_usage("provider1", "model1", 100, 50, "/test-endpoint")

    mock_sent.labels.assert_called_once_with("provider1", "model1", "/test-endpoint")
    mock_sent.labels.return_value.inc.assert_called_once_with(100)
    mock_received.labels.assert_called_once_with(
        "provider1", "model1", "/test-endpoint"
    )
    mock_received.labels.return_value.inc.assert_called_once_with(50)


def test_record_llm_token_usage_logs_metric_errors(mocker: MockerFixture) -> None:
    """Test that token metric failures are logged and swallowed."""
    mock_sent = mocker.patch("metrics.recording.metrics.llm_token_sent_total")
    mock_sent.labels.return_value.inc.side_effect = ValueError("bad")
    mocker.patch("metrics.recording.metrics.llm_token_received_total")
    mock_logger = mocker.patch("metrics.recording.logger")

    recording.record_llm_token_usage("provider1", "model1", 100, 50, "/test-endpoint")

    mock_logger.warning.assert_called_once_with(
        "Failed to update token metrics", exc_info=True
    )


def test_record_auth_attempt_records_counter(mocker: MockerFixture) -> None:
    """Test that authentication attempt recording increments the counter."""
    mock_metric = mocker.patch("metrics.recording.metrics.auth_attempts_total")

    recording.record_auth_attempt("rh-identity", "success", "authenticated")

    mock_metric.labels.assert_called_once_with(
        "rh-identity", "success", "authenticated"
    )
    mock_metric.labels.return_value.inc.assert_called_once()


def test_record_auth_attempt_logs_metric_errors(mocker: MockerFixture) -> None:
    """Test that authentication attempt metric failures are logged and swallowed."""
    mock_metric = mocker.patch("metrics.recording.metrics.auth_attempts_total")
    mock_metric.labels.return_value.inc.side_effect = AttributeError("missing")
    mock_logger = mocker.patch("metrics.recording.logger")

    recording.record_auth_attempt("rh-identity", "failure", "missing_header")

    mock_logger.warning.assert_called_once_with(
        "Failed to update authentication metric", exc_info=True
    )


def test_record_auth_duration_records_histogram(mocker: MockerFixture) -> None:
    """Test that authentication duration recording observes the histogram."""
    mock_metric = mocker.patch("metrics.recording.metrics.auth_duration_seconds")

    recording.record_auth_duration("rh-identity", "success", 0.5)

    mock_metric.labels.assert_called_once_with("rh-identity", "success")
    mock_metric.labels.return_value.observe.assert_called_once_with(0.5)


def test_record_auth_duration_logs_metric_errors(mocker: MockerFixture) -> None:
    """Test that authentication duration metric failures are logged and swallowed."""
    mock_metric = mocker.patch("metrics.recording.metrics.auth_duration_seconds")
    mock_metric.labels.return_value.observe.side_effect = TypeError("bad")
    mock_logger = mocker.patch("metrics.recording.logger")

    recording.record_auth_duration("rh-identity", "failure", 0.5)

    mock_logger.warning.assert_called_once_with(
        "Failed to update authentication duration metric", exc_info=True
    )


def test_record_authorization_check_records_counter(mocker: MockerFixture) -> None:
    """Test that authorization check recording increments the counter."""
    mock_metric = mocker.patch("metrics.recording.metrics.authorization_checks_total")

    recording.record_authorization_check("responses", "success")

    mock_metric.labels.assert_called_once_with("responses", "success")
    mock_metric.labels.return_value.inc.assert_called_once()


def test_record_authorization_check_logs_metric_errors(mocker: MockerFixture) -> None:
    """Test that authorization check metric failures are logged and swallowed."""
    mock_metric = mocker.patch("metrics.recording.metrics.authorization_checks_total")
    mock_metric.labels.return_value.inc.side_effect = ValueError("bad")
    mock_logger = mocker.patch("metrics.recording.logger")

    recording.record_authorization_check("responses", "denied")

    mock_logger.warning.assert_called_once_with(
        "Failed to update authorization metric", exc_info=True
    )


def test_record_authorization_duration_records_histogram(
    mocker: MockerFixture,
) -> None:
    """Test that authorization duration recording observes the histogram."""
    mock_metric = mocker.patch(
        "metrics.recording.metrics.authorization_duration_seconds"
    )

    recording.record_authorization_duration("responses", "success", 0.25)

    mock_metric.labels.assert_called_once_with("responses", "success")
    mock_metric.labels.return_value.observe.assert_called_once_with(0.25)


def test_record_authorization_duration_logs_metric_errors(
    mocker: MockerFixture,
) -> None:
    """Test that authorization duration metric failures are logged and swallowed."""
    mock_metric = mocker.patch(
        "metrics.recording.metrics.authorization_duration_seconds"
    )
    mock_metric.labels.return_value.observe.side_effect = AttributeError("missing")
    mock_logger = mocker.patch("metrics.recording.logger")

    recording.record_authorization_duration("responses", "error", 0.25)

    mock_logger.warning.assert_called_once_with(
        "Failed to update authorization duration metric", exc_info=True
    )


def test_record_quota_check_records_counter_and_histogram(
    mocker: MockerFixture,
) -> None:
    """Test that quota check recording updates counter and duration metrics."""
    mock_counter = mocker.patch("metrics.recording.metrics.quota_checks_total")
    mock_histogram = mocker.patch(
        "metrics.recording.metrics.quota_check_duration_seconds"
    )

    recording.record_quota_check("/v1/infer", "org_id", "success", 0.75)

    mock_counter.labels.assert_called_once_with("/v1/infer", "org_id", "success")
    mock_counter.labels.return_value.inc.assert_called_once()
    mock_histogram.labels.assert_called_once_with("/v1/infer", "org_id", "success")
    mock_histogram.labels.return_value.observe.assert_called_once_with(0.75)


def test_record_quota_check_logs_metric_errors(mocker: MockerFixture) -> None:
    """Test that quota check metric failures are logged and swallowed."""
    mock_counter = mocker.patch("metrics.recording.metrics.quota_checks_total")
    mock_counter.labels.return_value.inc.side_effect = TypeError("bad")
    mocker.patch("metrics.recording.metrics.quota_check_duration_seconds")
    mock_logger = mocker.patch("metrics.recording.logger")

    recording.record_quota_check("/v1/infer", "org_id", "failure", 0.75)

    mock_logger.warning.assert_called_once_with(
        "Failed to update quota check metrics", exc_info=True
    )


def test_record_llm_inference_duration_records_histogram(
    mocker: MockerFixture,
) -> None:
    """Test that LLM inference duration recording observes the histogram."""
    mock_metric = mocker.patch(
        "metrics.recording.metrics.llm_inference_duration_seconds"
    )

    recording.record_llm_inference_duration(
        "vertexai", "gemini", "/v1/responses", "success", 1.5
    )

    mock_metric.labels.assert_called_once_with(
        "vertexai", "gemini", "/v1/responses", "success"
    )
    mock_metric.labels.return_value.observe.assert_called_once_with(1.5)


def test_record_llm_inference_duration_logs_metric_errors(
    mocker: MockerFixture,
) -> None:
    """Test that LLM inference duration metric failures are logged and swallowed."""
    mock_metric = mocker.patch(
        "metrics.recording.metrics.llm_inference_duration_seconds"
    )
    mock_metric.labels.return_value.observe.side_effect = ValueError("bad")
    mock_logger = mocker.patch("metrics.recording.logger")

    recording.record_llm_inference_duration(
        "vertexai", "gemini", "/v1/responses", "failure", 1.5
    )

    mock_logger.warning.assert_called_once_with(
        "Failed to update LLM inference duration metric", exc_info=True
    )

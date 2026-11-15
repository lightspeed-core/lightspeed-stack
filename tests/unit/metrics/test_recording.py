"""Unit tests for Prometheus metric recording helpers."""

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from pytest_mock import MockerFixture, MockType

from metrics import recording


@dataclass(frozen=True)
class HistogramRecorderCase:
    """Expected behavior for a histogram-style metric recorder."""

    metric_path: str
    recorder: Callable[..., None]
    args: tuple[object, ...]
    labels: tuple[object, ...]
    duration: float
    warning_message: str


def test_measure_response_duration_records_timer(mocker: MockerFixture) -> None:
    """Time response handling with the endpoint path used as the metric label."""
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
    """Keep request handling alive when timer setup fails."""
    mock_metric = mocker.patch("metrics.recording.metrics.response_duration_seconds")
    mock_metric.labels.return_value.time.side_effect = AttributeError("missing")
    mock_logger = mocker.patch("metrics.recording.logger")

    with recording.measure_response_duration("/v1/infer"):
        pass

    mock_logger.warning.assert_called_once_with(
        "Failed to start response duration metric", exc_info=True
    )


def test_record_rest_api_call_records_counter(mocker: MockerFixture) -> None:
    """Count REST calls by endpoint path and status code."""
    mock_metric = mocker.patch("metrics.recording.metrics.rest_api_calls_total")

    recording.record_rest_api_call("/v1/infer", 200)

    mock_metric.labels.assert_called_once_with("/v1/infer", 200)
    mock_metric.labels.return_value.inc.assert_called_once()


def test_record_rest_api_call_logs_metric_errors(mocker: MockerFixture) -> None:
    """Log counter failures without surfacing metric errors to callers."""
    mock_metric = mocker.patch("metrics.recording.metrics.rest_api_calls_total")
    mock_metric.labels.return_value.inc.side_effect = AttributeError("missing")
    mock_logger = mocker.patch("metrics.recording.logger")

    recording.record_rest_api_call("/v1/infer", 200)

    mock_logger.warning.assert_called_once_with(
        "Failed to update REST API call metric", exc_info=True
    )


def test_record_llm_call_records_counter(mocker: MockerFixture) -> None:
    """Count LLM calls by provider, model, and endpoint path."""
    mock_metric = mocker.patch("metrics.recording.metrics.llm_calls_total")

    recording.record_llm_call("provider1", "model1", "/test-endpoint")

    mock_metric.labels.assert_called_once_with("provider1", "model1", "/test-endpoint")
    mock_metric.labels.return_value.inc.assert_called_once()


def test_record_llm_call_logs_metric_errors(mocker: MockerFixture) -> None:
    """Log LLM call metric failures without interrupting request flow."""
    mock_metric = mocker.patch("metrics.recording.metrics.llm_calls_total")
    mock_metric.labels.return_value.inc.side_effect = AttributeError("missing")
    mock_logger = mocker.patch("metrics.recording.logger")

    recording.record_llm_call("provider1", "model1", "/test-endpoint")

    mock_logger.warning.assert_called_once_with(
        "Failed to update LLM call metric", exc_info=True
    )


def test_record_llm_failure_records_counter(mocker: MockerFixture) -> None:
    """Count failed LLM calls using the same labels as successful calls."""
    mock_metric = mocker.patch("metrics.recording.metrics.llm_calls_failures_total")

    recording.record_llm_failure("provider1", "model1", "/test-endpoint")

    mock_metric.labels.assert_called_once_with("provider1", "model1", "/test-endpoint")
    mock_metric.labels.return_value.inc.assert_called_once()


def test_record_llm_failure_logs_metric_errors(mocker: MockerFixture) -> None:
    """Suppress failures from the LLM failure counter after logging them."""
    mock_metric = mocker.patch("metrics.recording.metrics.llm_calls_failures_total")
    mock_metric.labels.return_value.inc.side_effect = TypeError("bad")
    mock_logger = mocker.patch("metrics.recording.logger")

    recording.record_llm_failure("provider1", "model1", "/test-endpoint")

    mock_logger.warning.assert_called_once_with(
        "Failed to update LLM failure metric", exc_info=True
    )


def test_record_llm_validation_error_records_counter(mocker: MockerFixture) -> None:
    """Count LLM validation errors against the originating endpoint path."""
    mock_metric = mocker.patch(
        "metrics.recording.metrics.llm_calls_validation_errors_total"
    )

    recording.record_llm_validation_error("/test-endpoint")

    mock_metric.labels.assert_called_once_with("/test-endpoint")
    mock_metric.labels.return_value.inc.assert_called_once()


def test_record_llm_validation_error_logs_metric_errors(
    mocker: MockerFixture,
) -> None:
    """Keep validation-error metric failures from escaping the helper."""
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
    """Record sent and received token totals under matching LLM labels."""
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
    """Stop token metric failures from breaking the caller path."""
    mock_sent = mocker.patch("metrics.recording.metrics.llm_token_sent_total")
    mock_sent.labels.return_value.inc.side_effect = ValueError("bad")
    mocker.patch("metrics.recording.metrics.llm_token_received_total")
    mock_logger = mocker.patch("metrics.recording.logger")

    recording.record_llm_token_usage("provider1", "model1", 100, 50, "/test-endpoint")

    mock_logger.warning.assert_called_once_with(
        "Failed to update token metrics", exc_info=True
    )


@pytest.fixture(name="recording_logger")
def recording_logger_fixture(mocker: MockerFixture) -> MockType:
    """Patch the metric recording logger for failure assertions."""
    return mocker.patch("metrics.recording.logger")


@pytest.mark.parametrize(
    "case",
    [
        HistogramRecorderCase(
            metric_path="metrics.recording.metrics.llm_inference_duration_seconds",
            recorder=recording.record_llm_inference_duration,
            args=("vertexai", "gemini", "/v1/responses", "success", 1.5),
            labels=("vertexai", "gemini", "/v1/responses", "success"),
            duration=1.5,
            warning_message="Failed to update LLM inference duration metric",
        ),
    ],
)
def test_histogram_recorders_observe_metrics_and_log_errors(
    mocker: MockerFixture,
    recording_logger: MockType,
    case: HistogramRecorderCase,
) -> None:
    """Exercise histogram helpers for both observation and failure logging."""
    mock_metric = mocker.patch(case.metric_path)

    case.recorder(*case.args)

    mock_metric.labels.assert_called_once_with(*case.labels)
    mock_metric.labels.return_value.observe.assert_called_once_with(case.duration)

    mock_metric.reset_mock()
    mock_metric.labels.return_value.observe.side_effect = TypeError("bad")
    case.recorder(*case.args)

    recording_logger.warning.assert_called_once_with(
        case.warning_message, exc_info=True
    )


def test_record_llm_inference_duration_bounds_result_label(
    mocker: MockerFixture,
) -> None:
    """Collapse unknown inference result labels to the failure bucket."""
    mock_metric = mocker.patch(
        "metrics.recording.metrics.llm_inference_duration_seconds"
    )

    recording.record_llm_inference_duration(
        "vertexai", "gemini", "/v1/responses", "timeout", 2.0
    )

    mock_metric.labels.assert_called_once_with(
        "vertexai", "gemini", "/v1/responses", "failure"
    )
    mock_metric.labels.return_value.observe.assert_called_once_with(2.0)

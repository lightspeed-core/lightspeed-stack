"""Unit tests for Prometheus metric recording helpers."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from pytest_mock import MockerFixture

from metrics import recording


@dataclass(frozen=True)
class CounterRecorderCase:
    """Expected behavior for a counter-style metric recorder."""

    metric_path: str
    recorder: Callable[..., None]
    args: tuple[object, ...]
    labels: tuple[object, ...]
    warning_message: str


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


@pytest.fixture(name="recording_logger")
def recording_logger_fixture(mocker: MockerFixture) -> Any:
    """Patch the metric recording logger for failure assertions."""
    return mocker.patch("metrics.recording.logger")


@pytest.mark.parametrize(
    "case",
    [
        CounterRecorderCase(
            metric_path="metrics.recording.metrics.auth_attempts_total",
            recorder=recording.record_auth_attempt,
            args=("rh-identity", "success", "authenticated"),
            labels=("rh-identity", "success", "authenticated"),
            warning_message="Failed to update authentication metric",
        ),
        CounterRecorderCase(
            metric_path="metrics.recording.metrics.authorization_checks_total",
            recorder=recording.record_authorization_check,
            args=("responses", "success"),
            labels=("responses", "success"),
            warning_message="Failed to update authorization metric",
        ),
    ],
)
def test_counter_recorders_update_metrics_and_log_errors(
    mocker: MockerFixture,
    recording_logger: Any,
    case: CounterRecorderCase,
) -> None:
    """Test new single-counter helpers with shared success and failure coverage."""
    mock_metric = mocker.patch(case.metric_path)

    case.recorder(*case.args)

    mock_metric.labels.assert_called_once_with(*case.labels)
    mock_metric.labels.return_value.inc.assert_called_once()

    mock_metric.reset_mock()
    mock_metric.labels.return_value.inc.side_effect = AttributeError("missing")
    case.recorder(*case.args)

    recording_logger.warning.assert_called_once_with(
        case.warning_message, exc_info=True
    )


@pytest.mark.parametrize(
    "case",
    [
        HistogramRecorderCase(
            metric_path="metrics.recording.metrics.auth_duration_seconds",
            recorder=recording.record_auth_duration,
            args=("rh-identity", "success", 0.5),
            labels=("rh-identity", "success"),
            duration=0.5,
            warning_message="Failed to update authentication duration metric",
        ),
        HistogramRecorderCase(
            metric_path="metrics.recording.metrics.authorization_duration_seconds",
            recorder=recording.record_authorization_duration,
            args=("responses", "success", 0.25),
            labels=("responses", "success"),
            duration=0.25,
            warning_message="Failed to update authorization duration metric",
        ),
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
    recording_logger: Any,
    case: HistogramRecorderCase,
) -> None:
    """Test new histogram helpers with shared success and failure coverage."""
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


@pytest.mark.parametrize("failing_metric", ["counter", "histogram"])
def test_record_quota_check_updates_metrics_and_logs_errors(
    mocker: MockerFixture,
    recording_logger: Any,
    failing_metric: str,
) -> None:
    """Test quota helper counter and histogram updates plus both failure points."""
    mock_counter = mocker.patch("metrics.recording.metrics.quota_checks_total")
    mock_histogram = mocker.patch(
        "metrics.recording.metrics.quota_check_duration_seconds"
    )

    recording.record_quota_check("/v1/infer", "org_id", "success", 0.75)

    mock_counter.labels.assert_called_once_with("/v1/infer", "org_id", "success")
    mock_counter.labels.return_value.inc.assert_called_once()
    mock_histogram.labels.assert_called_once_with("/v1/infer", "org_id", "success")
    mock_histogram.labels.return_value.observe.assert_called_once_with(0.75)

    mock_counter.reset_mock()
    mock_histogram.reset_mock()
    if failing_metric == "counter":
        mock_counter.labels.return_value.inc.side_effect = TypeError("bad")
    else:
        mock_histogram.labels.return_value.observe.side_effect = TypeError("bad")

    recording.record_quota_check("/v1/infer", "org_id", "failure", 0.75)

    recording_logger.warning.assert_called_once_with(
        "Failed to update quota check metrics", exc_info=True
    )

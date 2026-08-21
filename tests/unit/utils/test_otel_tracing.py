"""Unit tests for utils/otel_tracing.py functions."""

import re
from collections.abc import Generator
from typing import Any

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from utils.otel_tracing import (
    SpanAttributes,
    SpanEvents,
    add_span_event,
    anonymize_value,
    record_exception,
    set_span_attributes,
)


@pytest.fixture(name="otel")
def otel_fixture() -> Generator[Any, Any, Any]:
    """Provides an isolated tracer and exporter instance."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("unit-test-tracer")

    yield tracer, exporter

    exporter.clear()
    provider.shutdown()


class TestAnonymizeValue:
    """Tests for anonymize_value function."""

    def test_short_string_no_content_leak(self) -> None:
        """Test that short strings are fully anonymized with no content leak."""
        input_value = "MySensitiveData"
        result = anonymize_value(input_value, max_length=50)
        # Verify the actual input content doesn't appear (not just hash metadata)
        assert "MySensitiveData" not in result
        assert "Sensitive" not in result
        assert "[hash:" in result
        assert ":short:" in result
        assert f"len={len(input_value)}]" in result

    def test_long_string_no_content_leak(self) -> None:
        """Test that long strings are fully anonymized with no content leak."""
        input_value = "ThisIsVeryLongSensitiveUserInputThatExceedsMaxLength" * 2
        result = anonymize_value(input_value, max_length=50)
        # Verify the actual input content doesn't appear
        assert "ThisIsVeryLongSensitiveUserInputThatExceedsMaxLength" not in result
        assert "Sensitive" not in result
        assert "UserInput" not in result
        assert "[hash:" in result
        assert ":long:" in result
        assert f"len={len(input_value)}]" in result

    def test_exact_max_length_classified_as_long(self) -> None:
        """Test the max_length boundary: 50 chars = short, 51 chars = long."""
        # Test at exactly max_length (50 chars) - should be short
        input_at_boundary = "BoundaryTest" * 4 + "12"  # Exactly 50 chars
        result_at_boundary = anonymize_value(input_at_boundary, max_length=50)
        assert "BoundaryTest" not in result_at_boundary  # No content leak
        assert ":short:" in result_at_boundary
        assert "len=50]" in result_at_boundary

        # Test at max_length + 1 (51 chars) - should be long
        input_over_boundary = "OverBoundaryTest" * 3 + "123"  # Exactly 51 chars
        result_over_boundary = anonymize_value(input_over_boundary, max_length=50)
        assert "OverBoundaryTest" not in result_over_boundary  # No content leak
        assert ":long:" in result_over_boundary
        assert "len=51]" in result_over_boundary

    def test_custom_max_length(self) -> None:
        """Test with custom max_length parameter."""
        input_value = "PersonalIdentifiableInformation"
        result = anonymize_value(input_value, max_length=4)
        assert "PersonalIdentifiableInformation" not in result
        assert "Personal" not in result
        assert ":long:" in result
        assert f"len={len(input_value)}]" in result

    def test_empty_string(self) -> None:
        """Test with empty string."""
        result = anonymize_value("", max_length=50)
        assert "[hash:" in result
        assert ":short:" in result
        assert "len=0]" in result

    def test_hash_consistency(self) -> None:
        """Test that same input produces same hash digest."""
        input_str = "RepeatedSensitiveValue" * 20
        result1 = anonymize_value(input_str, max_length=10)
        result2 = anonymize_value(input_str, max_length=10)
        assert result1 == result2
        # Verify no content leak
        assert "RepeatedSensitiveValue" not in result1
        assert "Sensitive" not in result1

    def test_hash_uniqueness(self) -> None:
        """Test that different inputs produce different hashes."""
        result1 = anonymize_value("ConfidentialUserQuery1")
        result2 = anonymize_value("ConfidentialUserQuery2")
        assert result1 != result2
        # Verify no content leak
        assert "ConfidentialUserQuery" not in result1
        assert "ConfidentialUserQuery" not in result2
        assert "Confidential" not in result1
        assert "Confidential" not in result2

    def test_hmac_deterministic_with_env_secret(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that HMAC produces deterministic results with environment secret."""
        # Set a known secret
        monkeypatch.setenv("OTEL_ANONYMIZATION_SECRET", "test-secret-key")
        input_value = "SensitiveData"
        result1 = anonymize_value(input_value)
        result2 = anonymize_value(input_value)
        # Same input with same secret should produce identical output
        assert result1 == result2
        # Verify no content leak
        assert "SensitiveData" not in result1
        # Verify it's using 16 hex chars (64 bits)
        match = re.search(r"\[hash:([0-9a-f]+):", result1)
        assert match is not None
        assert len(match.group(1)) == 16  # 16 hex chars = 64 bits

    def test_missing_secret_raises_error(self, monkeypatch):
        """Test that missing OTEL_ANONYMIZATION_SECRET raises a clear error."""
        # Remove the secret that was set by the autouse fixture
        monkeypatch.delenv("OTEL_ANONYMIZATION_SECRET", raising=False)
        # Ensure OTEL SDK is not disabled
        monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
        with pytest.raises(
            ValueError,
            match=r"OTEL anonymization secret not configured.*OTEL_ANONYMIZATION_SECRET",
        ):
            anonymize_value("test-value")

    def test_missing_secret_with_otel_disabled_returns_placeholder(self, monkeypatch):
        """Test that missing secret with OTEL_SDK_DISABLED returns placeholder."""
        monkeypatch.delenv("OTEL_ANONYMIZATION_SECRET", raising=False)
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
        result = anonymize_value("test-value")
        assert result == "[otel-disabled:len=10]"
        assert "test-value" not in result


class TestSetSpanAttributes:
    """Tests for set_span_attributes function."""

    def test_set_single_attribute(self, otel):
        """Test setting a single attribute on a span."""
        tracer, exporter = otel
        with tracer.start_as_current_span("test_span") as span:
            set_span_attributes(span, {SpanAttributes.SESSION_ID: "test-session-123"})

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].attributes[SpanAttributes.SESSION_ID] == "test-session-123"

    def test_set_multiple_attributes(self, otel):
        """Test setting multiple attributes on a span."""
        tracer, exporter = otel
        with tracer.start_as_current_span("test_span") as span:
            set_span_attributes(
                span,
                {
                    SpanAttributes.USER_ID: "user-456",
                    SpanAttributes.LLM_MODEL_ID: "gpt-4o-mini",
                    SpanAttributes.LLM_USAGE_INPUT_TOKENS: 100,
                    SpanAttributes.LLM_USAGE_OUTPUT_TOKENS: 50,
                },
            )

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        attrs = spans[0].attributes
        assert attrs[SpanAttributes.USER_ID] == "user-456"
        assert attrs[SpanAttributes.LLM_MODEL_ID] == "gpt-4o-mini"
        assert attrs[SpanAttributes.LLM_USAGE_INPUT_TOKENS] == 100
        assert attrs[SpanAttributes.LLM_USAGE_OUTPUT_TOKENS] == 50

    def test_set_attributes_with_list(self, otel):
        """Test setting attributes with list values."""
        tracer, exporter = otel
        with tracer.start_as_current_span("test_span") as span:
            set_span_attributes(
                span,
                {
                    SpanAttributes.RAG_SOURCES: [
                        "http://example.com/doc1",
                        "http://example.com/doc2",
                    ],
                    SpanAttributes.TOOL_CALLS_NAMES: ["search", "calculator"],
                },
            )

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        attrs = spans[0].attributes
        # OTel standardizes sequences as tuples internally
        assert attrs[SpanAttributes.RAG_SOURCES] == (
            "http://example.com/doc1",
            "http://example.com/doc2",
        )
        assert attrs[SpanAttributes.TOOL_CALLS_NAMES] == ("search", "calculator")

    def test_set_empty_attributes(self, otel):
        """Test setting empty attributes dict."""
        tracer, exporter = otel
        with tracer.start_as_current_span("test_span") as span:
            set_span_attributes(span, {})

        spans = exporter.get_finished_spans()
        assert len(spans) == 1


class TestAddSpanEvent:
    """Tests for add_span_event function."""

    def test_add_event_without_attributes(self, otel):
        """Test adding an event without additional attributes."""
        tracer, exporter = otel
        with tracer.start_as_current_span("test_span") as span:
            add_span_event(span, SpanEvents.VALIDATION_COMPLETED)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        events = spans[0].events
        assert len(events) == 1
        assert events[0].name == SpanEvents.VALIDATION_COMPLETED
        assert events[0].attributes == {}

    def test_add_event_with_attributes(self, otel):
        """Test adding an event with additional attributes."""
        tracer, exporter = otel
        with tracer.start_as_current_span("test_span") as span:
            add_span_event(
                span,
                SpanEvents.SHIELD_REJECTED,
                {
                    "shield.id": "test-shield",
                    "shield.categories": "violence,hate",
                },
            )

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        events = spans[0].events
        assert len(events) == 1
        assert events[0].name == SpanEvents.SHIELD_REJECTED
        assert events[0].attributes["shield.id"] == "test-shield"
        assert events[0].attributes["shield.categories"] == "violence,hate"

    def test_add_multiple_events(self, otel):
        """Test adding multiple events to a span."""
        tracer, exporter = otel
        with tracer.start_as_current_span("test_span") as span:
            add_span_event(span, SpanEvents.LLM_INFERENCE_STARTED)
            add_span_event(
                span, SpanEvents.RAG_RETRIEVAL_COMPLETED, {"rag.chunks.count": 5}
            )
            add_span_event(span, SpanEvents.LLM_INFERENCE_COMPLETED)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        events = spans[0].events
        assert len(events) == 3
        assert events[0].name == SpanEvents.LLM_INFERENCE_STARTED
        assert events[1].name == SpanEvents.RAG_RETRIEVAL_COMPLETED
        assert events[1].attributes["rag.chunks.count"] == 5
        assert events[2].name == SpanEvents.LLM_INFERENCE_COMPLETED


class TestRecordException:
    """Tests for record_exception function."""

    def test_record_exception_basic(self, otel):
        """Test recording a basic exception on a span."""
        tracer, exporter = otel
        test_exception = ValueError("Test error message")

        with tracer.start_as_current_span("test_span") as span:
            record_exception(span, test_exception)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        events = spans[0].events
        assert len(events) == 1
        assert events[0].name == "exception"
        assert events[0].attributes["exception.type"] == "ValueError"
        assert events[0].attributes["exception.message"] == "Test error message"
        assert "exception.stacktrace" in events[0].attributes

    def test_record_exception_with_custom_attributes(self, otel):
        """Test recording an exception with custom attributes."""
        tracer, exporter = otel
        test_exception = RuntimeError("Runtime error")

        with tracer.start_as_current_span("test_span") as span:
            record_exception(
                span,
                test_exception,
                {SpanAttributes.RESPONSE_ERROR: "quota_check"},
            )

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        events = spans[0].events
        assert len(events) == 1
        assert events[0].name == "exception"
        assert events[0].attributes["exception.type"] == "RuntimeError"
        assert events[0].attributes[SpanAttributes.RESPONSE_ERROR] == "quota_check"

    def test_record_multiple_exceptions(self, otel):
        """Test recording multiple exceptions on a span."""
        tracer, exporter = otel

        with tracer.start_as_current_span("test_span") as span:
            record_exception(span, ValueError("First error"))
            record_exception(span, RuntimeError("Second error"))

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        events = spans[0].events
        assert len(events) == 2
        assert events[0].attributes["exception.type"] == "ValueError"
        assert events[0].attributes["exception.message"] == "First error"
        assert events[1].attributes["exception.type"] == "RuntimeError"
        assert events[1].attributes["exception.message"] == "Second error"

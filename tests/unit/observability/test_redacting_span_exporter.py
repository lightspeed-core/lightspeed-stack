"""Unit tests for the in-process redacting span exporter."""

from collections.abc import Callable
from typing import Any

import pytest
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as GRPCSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HTTPSpanExporter,
)
from opentelemetry.sdk.trace.export import SpanExportResult
from pytest_mock import MockerFixture

from observability.redacting_span_exporter import (
    RedactingSpanExporter,
    _default_otlp_exporter,
)


class _FakeSpan:  # pylint: disable=too-few-public-methods
    """Minimal stand-in for a ReadableSpan: exposes .name, .attributes, ._attributes."""

    def __init__(self, attributes: dict, name: str = "test.span") -> None:
        self._attributes = dict(attributes)
        self.name = name

    @property
    def attributes(self) -> dict:
        """Return the span's attribute mapping, as ReadableSpan does."""
        return self._attributes


def _make_exporter(
    mocker: MockerFixture,
    anonymize_side_effect: Callable[[str], str] | None = None,
) -> tuple[RedactingSpanExporter, Any, Any]:
    """Build a RedactingSpanExporter with a mocked delegate and anonymizer."""
    delegate = mocker.Mock()
    delegate.export.return_value = SpanExportResult.SUCCESS
    anonymizer = mocker.Mock()
    anonymizer.anonymize_text.side_effect = anonymize_side_effect or (
        lambda text: text.replace("sam@redhat.com", "<EMAIL_ADDRESS>")
    )
    exporter = RedactingSpanExporter(delegate=delegate, anonymizer=anonymizer)
    return exporter, delegate, anonymizer


def test_redacts_content_attributes_and_delegates(mocker: MockerFixture) -> None:
    """Content attributes are redacted; other attributes and the span pass through."""
    exporter, delegate, _ = _make_exporter(mocker)
    span = _FakeSpan(
        {
            "request.input": "sam@redhat.com asks about K8s",
            "response.output": "hello sam@redhat.com",
            "llm.model.id": "gpt-4o-mini",
        }
    )

    result = exporter.export([span])

    assert result is SpanExportResult.SUCCESS
    assert span.attributes["request.input"] == "<EMAIL_ADDRESS> asks about K8s"
    assert span.attributes["response.output"] == "hello <EMAIL_ADDRESS>"
    assert span.attributes["llm.model.id"] == "gpt-4o-mini"
    delegate.export.assert_called_once_with([span])


def test_skips_missing_non_string_and_empty_values(mocker: MockerFixture) -> None:
    """Empty, non-string, and absent content attributes are left alone."""
    exporter, _, anonymizer = _make_exporter(mocker)
    span = _FakeSpan({"request.input": "", "rag.input": 123})

    exporter.export([span])

    anonymizer.anonymize_text.assert_not_called()
    assert span.attributes == {"request.input": "", "rag.input": 123}


def test_fail_closed_drops_span_on_redaction_error(mocker: MockerFixture) -> None:
    """A redaction error drops the span (fail closed): it is never exported."""

    def boom(_text: str) -> str:
        raise RuntimeError("anonymizer unavailable")

    exporter, delegate, _ = _make_exporter(mocker, anonymize_side_effect=boom)
    span = _FakeSpan({"request.input": "sam@redhat.com"})

    result = exporter.export([span])

    delegate.export.assert_not_called()
    assert result is SpanExportResult.SUCCESS


def test_fail_closed_drops_only_the_failing_span(mocker: MockerFixture) -> None:
    """A span whose redaction fails is dropped; healthy spans still export."""

    def selective(text: str) -> str:
        if "boom" in text:
            raise RuntimeError("anonymizer unavailable")
        return text.replace("sam@redhat.com", "<EMAIL_ADDRESS>")

    exporter, delegate, _ = _make_exporter(mocker, anonymize_side_effect=selective)
    good = _FakeSpan({"request.input": "contact sam@redhat.com"})
    bad = _FakeSpan({"request.input": "boom trigger"})

    result = exporter.export([good, bad])

    assert result is SpanExportResult.SUCCESS
    delegate.export.assert_called_once_with([good])
    assert good.attributes["request.input"] == "contact <EMAIL_ADDRESS>"


def test_shutdown_and_force_flush_delegate(mocker: MockerFixture) -> None:
    """shutdown and force_flush delegate to the downstream exporter."""
    exporter, delegate, _ = _make_exporter(mocker)

    exporter.shutdown()
    delegate.shutdown.assert_called_once()

    exporter.force_flush(1234)
    delegate.force_flush.assert_called_once_with(1234)


def test_default_exporter_defaults_to_grpc(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no protocol set, the default delegate is the gRPC OTLP exporter."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_PROTOCOL", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", raising=False)
    assert isinstance(_default_otlp_exporter(), GRPCSpanExporter)


def test_default_exporter_honors_http_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf selects the HTTP OTLP exporter."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    assert isinstance(_default_otlp_exporter(), HTTPSpanExporter)

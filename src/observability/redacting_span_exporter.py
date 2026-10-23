"""Span exporter that redacts PII from span content before delegating to OTLP.

In-process (producer-side) sanitization: redaction happens inside lightspeed-core,
before spans leave the process, so no unredacted span is ever put on the wire.

It is wired via the ``opentelemetry_traces_exporter`` entry point, selected with
``OTEL_TRACES_EXPORTER=redacting_otlp``. Auto-instrumentation
(``opentelemetry-instrument``) instantiates it and wraps it in the
``BatchSpanProcessor``, so ``export()`` runs on the processor's background thread,
off the request path. The request/handler code is unchanged.

Redaction is delegated to the shared ``lightspeed-data-anonymizer`` engine
(Presidio + spaCy). The spaCy model must be installed separately, e.g.
``python -m spacy download en_core_web_lg``.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from lightspeed_data_anonymizer.anonymizer import PIIAnonymizer
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter as GRPCSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as HTTPSpanExporter,
)
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from log import get_logger

logger = get_logger(__name__)

# Span attributes whose string values may carry PII (see utils.otel_tracing).
CONTENT_ATTRIBUTES: tuple[str, ...] = (
    "request.input",
    "response.output",
    "rag.input",
)


def _default_otlp_exporter() -> SpanExporter:
    """Return an OTLP span exporter matching the configured protocol.

    Matches the stock SDK's supported values exactly: ``grpc`` (default) or
    ``http/protobuf``. Both read the standard ``OTEL_EXPORTER_OTLP_*`` environment
    for endpoint, headers, and TLS. Any other value (e.g. ``http/json``, which
    neither OTLP span exporter supports) is rejected rather than silently sending
    protobuf.

    Returns:
        A gRPC or HTTP OTLP span exporter.

    Raises:
        ValueError: if the configured protocol is not ``grpc`` or ``http/protobuf``.

    """
    protocol = (
        (
            os.getenv("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL")
            or os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL")
            or "grpc"
        )
        .strip()
        .lower()
    )
    if protocol == "grpc":
        return GRPCSpanExporter()
    if protocol == "http/protobuf":
        return HTTPSpanExporter()
    raise ValueError(
        f"unsupported OTEL_EXPORTER_OTLP_PROTOCOL {protocol!r}; "
        "supported values are 'grpc' and 'http/protobuf'"
    )


class RedactingSpanExporter(SpanExporter):
    """Wraps an OTLP span exporter, redacting content attributes before export.

    Attributes:
        delegate: The downstream exporter that actually ships the (redacted) spans.

    """

    def __init__(
        self,
        delegate: SpanExporter | None = None,
        anonymizer: PIIAnonymizer | None = None,
    ) -> None:
        """Initialize the exporter.

        Args:
            delegate: Downstream exporter. Defaults to an OTLP exporter matching
                ``OTEL_EXPORTER_OTLP_PROTOCOL`` (gRPC or HTTP), which reads the
                standard ``OTEL_EXPORTER_OTLP_*`` environment.
            anonymizer: Redaction engine. Defaults to a ``PIIAnonymizer``, which
                loads the spaCy model once at construction (off the request path).
                Injectable for testing.

        """
        self._delegate = delegate or _default_otlp_exporter()
        self._anonymizer = anonymizer or PIIAnonymizer()
        logger.info(
            "RedactingSpanExporter active; content attributes redacted in-process"
        )

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Redact content attributes, then delegate the export.

        Fail closed: if redaction of a span raises, that span is dropped rather
        than exported unredacted, so a redaction failure can never leak PII. Other
        spans in the batch are still exported.

        Args:
            spans: The spans to redact and export.

        Returns:
            The delegate's export result, or ``SUCCESS`` if every span was dropped
            (reporting failure would only make the batch processor retry the same
            failing spans).

        """
        safe_spans: list[ReadableSpan] = []
        for span in spans:
            try:
                self._redact_span(span)
            except Exception:  # pylint: disable=broad-except  # noqa: BLE001
                # Log the span name only, never the content being redacted.
                logger.error(
                    "in-process redaction failed for span %r; dropping it to avoid "
                    "exporting unredacted PII",
                    span.name,
                )
                continue
            safe_spans.append(span)

        if not safe_spans:
            return SpanExportResult.SUCCESS
        return self._delegate.export(safe_spans)

    def _redact_span(self, span: ReadableSpan) -> None:
        """Rewrite the content attributes of a span in place with redacted text.

        Args:
            span: The span whose content attributes are redacted in place.

        Raises:
            Exception: if the redaction engine fails. The caller drops the span
                (fail closed) rather than exporting unredacted content.

        """
        attributes = span.attributes
        if not attributes:
            return

        new_attributes = dict(attributes)
        changed = False
        for key in CONTENT_ATTRIBUTES:
            value = new_attributes.get(key)
            if not isinstance(value, str) or not value:
                continue
            redacted = self._anonymizer.anonymize_text(value)
            if redacted != value:
                new_attributes[key] = redacted
                changed = True

        if changed:
            # ReadableSpan exposes attributes via self._attributes; replacing it
            # with a plain dict is what the OTLP encoder reads at export time.
            span._attributes = new_attributes  # pylint: disable=protected-access

    def shutdown(self) -> None:
        """Shut down the delegate exporter."""
        self._delegate.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        """Force-flush the delegate exporter."""
        return self._delegate.force_flush(timeout_millis)

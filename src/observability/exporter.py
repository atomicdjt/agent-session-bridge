from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
    SpanExportResult,
)


class TrackingSpanExporter(SpanExporter):
    """Retain export failure state so the CLI never reports a failed export as successful."""

    def __init__(self, delegate: SpanExporter):
        self.delegate = delegate
        self.failed = False

    def export(self, spans):
        result = self.delegate.export(spans)
        if result is not SpanExportResult.SUCCESS:
            self.failed = True
        return result

    def shutdown(self):
        self.delegate.shutdown()

    def force_flush(self, timeout_millis: int = 30000):
        return self.delegate.force_flush(timeout_millis)


def setup_exporter(
    endpoint: str = "http://localhost:6006/v1/traces", console: bool = False
):
    """
    Setup the OpenTelemetry tracer provider and exporter.
    Default endpoint is the typical local Phoenix OTLP HTTP receiver.
    """
    resource = Resource.create({"service.name": "agent-session-bridge"})
    provider = TracerProvider(resource=resource)

    if console:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    if endpoint:
        otlp_exporter = TrackingSpanExporter(
            OTLPSpanExporter(endpoint=endpoint, timeout=2)
        )
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        setattr(provider, "asb_otlp_exporter", otlp_exporter)  # noqa: B010

    trace.set_tracer_provider(provider)
    return provider

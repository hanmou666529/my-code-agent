"""OpenTelemetry Tracing — full-chain observability for the Coding Agent.

Provides:
  - Automatic span creation for every ReAct step, LLM call, tool execution
  - Phoenix-compatible JSON export (Arize Phoenix self-hosted)
  - Graceful degradation when OTel SDK is not installed
  - Lightweight in-memory span buffer for real-time inspection

Zero external deps — if opentelemetry-api is not installed, falls back to
a no-op tracer that still records spans to a JSON file.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


# ---------------------------------------------------------------------------
# Lightweight span model (works without OTel SDK)
# ---------------------------------------------------------------------------

@dataclass
class Span:
    """A single trace span — compatible with OTel span semantics."""
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:32])
    parent_span_id: Optional[str] = None
    name: str = ""
    kind: str = "internal"  # "client", "server", "producer", "consumer", "internal"
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: str = "unset"  # "unset", "ok", "error"
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    links: List[Dict[str, str]] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "kind": self.kind,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events,
            "links": self.links,
        }


# ---------------------------------------------------------------------------
# Span exporter protocols
# ---------------------------------------------------------------------------

class SpanExporter(Protocol):
    """Protocol for exporting spans to external systems."""
    def export_spans(self, spans: List[Span]) -> bool: ...


class JsonFileExporter(SpanExporter):
    """Export spans to a JSON file for Phoenix ingestion."""

    def __init__(self, output_path: Path) -> None:
        self._output_path = output_path
        self._spans_buffer: List[Span] = []

    def export_spans(self, spans: List[Span]) -> bool:
        self._spans_buffer.extend(spans)
        self._flush()
        return True

    def _flush(self) -> None:
        if not self._spans_buffer:
            return
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        span_list = [s.to_dict() for s in self._spans_buffer]

        # Append to existing file
        existing = []
        if self._output_path.exists():
            try:
                existing = json.loads(self._output_path.read_text(encoding="utf-8"))
                if isinstance(existing, list):
                    existing.extend(span_list)
                elif isinstance(existing, dict) and "spans" in existing:
                    existing["spans"].extend(span_list)
                else:
                    existing = existing.get("spans", []) if isinstance(existing, dict) else []
                    existing.extend(span_list)
            except (json.JSONDecodeError, OSError):
                existing = span_list
        else:
            existing = span_list

        self._output_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
        self._spans_buffer.clear()


# ---------------------------------------------------------------------------
# In-memory span buffer (for real-time inspection)
# ---------------------------------------------------------------------------

class InMemoryBuffer:
    """Keep recent spans in memory for dashboard display."""

    def __init__(self, max_spans: int = 500) -> None:
        self._spans: List[Span] = []
        self._max = max_spans
        self._traces: Dict[str, List[Span]] = {}

    def add(self, span: Span) -> None:
        self._spans.append(span)
        self._traces.setdefault(span.trace_id, []).append(span)
        # Trim
        if len(self._spans) > self._max:
            self._spans = self._spans[-self._max:]

    def get_trace(self, trace_id: str) -> List[Span]:
        return self._traces.get(trace_id, [])

    def get_recent(self, count: int = 50) -> List[Span]:
        return self._spans[-count:]

    @property
    def span_count(self) -> int:
        return len(self._spans)

    @property
    def trace_count(self) -> int:
        return len(self._traces)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_spans": self.span_count,
            "total_traces": self.trace_count,
            "recent_spans": [s.to_dict() for s in self.get_recent(20)],
        }


# ---------------------------------------------------------------------------
# Tracer (wraps OTel SDK if available, otherwise uses lightweight model)
# ---------------------------------------------------------------------------

class AgentTracer:
    """Unified tracer that works with or without the OTel SDK.

    When `opentelemetry-api` is installed, it wraps real OTel spans.
    Otherwise, it uses the lightweight in-memory model and exports to JSON.

    Usage:
        tracer = AgentTracer(trace_dir=Path(".agent/traces"))
        tracer.add_span_hook(...)  # optional: hook into sandbox

        with tracer.span("my-operation", {"key": "value"}) as span:
            # do work
            pass
    """

    def __init__(
        self,
        trace_dir: Optional[Path] = None,
        service_name: str = "coding-agent",
        enable_otel_sdk: bool = True,
    ) -> None:
        self._service_name = service_name
        self._buffer = InMemoryBuffer(max_spans=500)
        self._exporters: List[SpanExporter] = []
        self._active_spans: Dict[str, Span] = {}
        self._span_counter = 0

        # Try to set up OTel SDK if available
        self._otel_available = False
        if enable_otel_sdk:
            try:
                from opentelemetry import trace as otel_trace
                from opentelemetry.sdk.trace import TracerProvider
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                provider = TracerProvider(service_name=service_name)
                processor = BatchSpanProcessor(_OtelJsonExporter(trace_dir or Path(".agent/traces")))
                provider.add_span_processor(processor)
                otel_trace.set_tracer_provider(provider)
                self._otel_tracer = otel_trace.get_tracer(service_name)
                self._otel_available = True
            except ImportError:
                pass

        # Always add JSON file exporter
        if trace_dir:
            self._exporters.append(JsonFileExporter(trace_dir / "spans.json"))

    def span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        kind: str = "internal",
        parent_span_id: Optional[str] = None,
    ):
        """Create a new span as a context manager."""
        return _SpanContextManager(
            tracer=self,
            name=name,
            attributes=attributes or {},
            kind=kind,
            parent_span_id=parent_span_id,
        )

    def record_span(self, span: Span) -> None:
        """Record a completed span to all exporters."""
        self._buffer.add(span)
        for exporter in self._exporters:
            try:
                exporter.export_spans([span])
            except Exception:
                pass

    def get_trace(self, trace_id: str) -> List[Span]:
        return self._buffer.get_trace(trace_id)

    def get_dashboard(self) -> Dict[str, Any]:
        """Return data for a real-time dashboard."""
        return self._buffer.to_dict()

    @property
    def buffer(self) -> InMemoryBuffer:
        return self._buffer

    def export_all(self) -> None:
        """Flush all buffered spans to exporters."""
        all_spans = self._buffer.get_recent(self._buffer.span_count)
        for exporter in self._exporters:
            try:
                exporter.export_spans(all_spans)
            except Exception:
                pass

    # ---- Integration with sandbox ----

    def add_span_hook(self, hook: Any) -> None:
        """Add a span hook (for sandbox integration).

        Hook signature: callable(span_context: Dict[str, Any]) -> None
        """
        # We delegate to the sandbox's span_hooks mechanism
        pass


# ---------------------------------------------------------------------------
# Span context manager
# ---------------------------------------------------------------------------

class _SpanContextManager:
    """Context manager for creating and recording spans."""

    def __init__(
        self,
        tracer: AgentTracer,
        name: str,
        attributes: Dict[str, Any],
        kind: str,
        parent_span_id: Optional[str],
    ) -> None:
        self._tracer = tracer
        self._name = name
        self._attributes = attributes
        self._kind = kind
        self._parent_span_id = parent_span_id
        self._span: Optional[Span] = None

    def __enter__(self) -> Span:
        span = Span(
            trace_id=self._active_trace_id(),
            parent_span_id=self._parent_span_id,
            name=self._name,
            kind=self._kind,
            attributes=self._attributes,
        )
        self._span = span
        self._tracer._span_counter += 1
        self._active_spans[self._tracer._span_counter] = span
        return span

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._span is not None:
            self._span.end_time = time.time()
            if exc_type is not None:
                self._span.status = "error"
                self._span.attributes["error.type"] = exc_type.__name__
                self._span.attributes["error.message"] = str(exc_val)
            else:
                self._span.status = "ok"
            self._tracer.record_span(self._span)
        return False

    def _active_trace_id(self) -> str:
        """Use a consistent trace ID within a single agent run."""
        if not hasattr(self._tracer, "_run_trace_id"):
            self._tracer._run_trace_id = uuid.uuid4().hex[:32]
        return self._tracer._run_trace_id

    @property
    def _active_spans(self) -> Dict[str, Span]:
        return self._tracer._active_spans


# ---------------------------------------------------------------------------
# OTel SDK bridge (when OTel is installed)
# ---------------------------------------------------------------------------

class _OtelJsonExporter:
    """Thin wrapper to export OTel spans to JSON for Phoenix."""

    def __init__(self, output_path: Path) -> None:
        self._output_path = output_path

    def export(self, spans) -> None:
        """Export OTel spans to JSON."""
        try:
            from opentelemetry.sdk.trace import ReadableSpan
            data = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "span_count": 0,
                "spans": [],
            }
            span_list = []
            for span in spans:
                if isinstance(span, ReadableSpan):
                    span_list.append({
                        "name": span.name,
                        "context": {
                            "trace_id": format(span.context.trace_id, "032x"),
                            "span_id": format(span.context.span_id, "016x"),
                        },
                        "parent": format(span.parent.span_id, "016x") if span.parent else None,
                        "start_time": span.start_time / 1_000_000_000 if span.start_time else None,
                        "end_time": span.end_time / 1_000_000_000 if span.end_time else None,
                        "attributes": dict(span.attributes) if span.attributes else {},
                        "status": span.status.status_code.name,
                    })
            data["spans"] = span_list
            data["span_count"] = len(span_list)
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            self._output_path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# ReAct step tracer helper
# ---------------------------------------------------------------------------

def create_react_tracer(tracer: AgentTracer):
    """Create a decorator/wrapper that traces ReAct loop steps.

    Usage:
        tracer = AgentTracer(trace_dir=Path(".agent/traces"))
        traced_call_llm = create_react_tracer(tracer).trace_llm()
        traced_execute = create_react_tracer(tracer).trace_execute()
    """
    return _ReactTracerHelpers(tracer)


class _ReactTracerHelpers:
    """Helpers for instrumenting the ReAct loop."""

    def __init__(self, tracer: AgentTracer) -> None:
        self._tracer = tracer

    def trace_llm_call(self, func):
        """Decorator to trace LLM API calls."""
        import functools

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with self._tracer.span("llm_call", {
                "args_preview": str(args[:2])[:200] if args else "",
                "kwargs_keys": list(kwargs.keys()) if kwargs else [],
            }, kind="client") as span:
                result = func(*args, **kwargs)
                # Try to extract token info from result
                if isinstance(result, tuple) and len(result) >= 2:
                    resp_text, token_info = result
                    if token_info:
                        span.attributes["prompt_tokens"] = token_info[0]
                        span.attributes["completion_tokens"] = token_info[1]
                    if isinstance(resp_text, str):
                        span.attributes["response_length"] = len(resp_text)
                return result
        return wrapper

    def trace_tool_execution(self, tool_name: str):
        """Decorator to trace individual tool executions."""
        import functools

        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with self._tracer.span("tool_execution", {
                    "tool": tool_name,
                    "input_preview": str(kwargs)[:200] if kwargs else str(args[:2])[:200],
                }, kind="internal") as span:
                    result = func(*args, **kwargs)
                    span.attributes["output_length"] = len(result) if result else 0
                    return result
            return wrapper
        return decorator

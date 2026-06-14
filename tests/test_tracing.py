"""Tests for OpenTelemetry Tracing — span creation, JSON export, in-memory buffer."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from my_code_agent.tracing import (
    AgentTracer,
    InMemoryBuffer,
    JsonFileExporter,
    Span,
    _ReactTracerHelpers,
    create_react_tracer,
)


# ---------------------------------------------------------------------------
# Span
# ---------------------------------------------------------------------------

class TestSpan:
    def test_basic_creation(self):
        span = Span(name="test-span", kind="client")
        assert span.name == "test-span"
        assert span.kind == "client"
        assert span.status == "unset"
        assert span.trace_id
        assert span.span_id

    def test_duration_before_end(self):
        span = Span(name="test")
        dur = span.duration_ms
        assert dur >= 0

    def test_duration_after_end(self):
        import time
        span = Span(name="test")
        span.end_time = time.time() + 1.0  # fake future
        assert span.duration_ms > 0

    def test_to_dict(self):
        span = Span(name="dict-test", attributes={"key": "val"})
        d = span.to_dict()
        assert d["name"] == "dict-test"
        assert d["attributes"]["key"] == "val"
        assert "duration_ms" in d


# ---------------------------------------------------------------------------
# InMemoryBuffer
# ---------------------------------------------------------------------------

class TestInMemoryBuffer:
    def test_add_and_get_recent(self):
        buf = InMemoryBuffer(max_spans=10)
        for i in range(5):
            buf.add(Span(name=f"span-{i}"))
        recent = buf.get_recent(3)
        assert len(recent) == 3
        assert recent[0].name == "span-2"

    def test_get_trace(self):
        buf = InMemoryBuffer()
        trace_id = "abc123"
        for i in range(3):
            s = Span(name=f"span-{i}", trace_id=trace_id)
            buf.add(s)
        trace = buf.get_trace(trace_id)
        assert len(trace) == 3

    def test_to_dict(self):
        buf = InMemoryBuffer()
        buf.add(Span(name="test"))
        d = buf.to_dict()
        assert d["total_spans"] == 1
        assert d["total_traces"] == 1
        assert "recent_spans" in d

    def test_max_spans_trim(self):
        buf = InMemoryBuffer(max_spans=3)
        for i in range(10):
            buf.add(Span(name=f"span-{i}"))
        assert buf.span_count <= 3

    def test_trace_count(self):
        buf = InMemoryBuffer()
        buf.add(Span(name="a", trace_id="t1"))
        buf.add(Span(name="b", trace_id="t1"))
        buf.add(Span(name="c", trace_id="t2"))
        assert buf.trace_count == 2


# ---------------------------------------------------------------------------
# JsonFileExporter
# ---------------------------------------------------------------------------

class TestJsonFileExporter:
    def test_export_and_file_created(self, tmp_path: Path):
        exporter = JsonFileExporter(tmp_path / "spans.json")
        spans = [Span(name="test-span", attributes={"key": "val"})]
        result = exporter.export_spans(spans)
        assert result is True
        assert (tmp_path / "spans.json").exists()
        data = (tmp_path / "spans.json").read_text()
        assert "test-span" in data

    def test_append_mode(self, tmp_path: Path):
        exporter = JsonFileExporter(tmp_path / "spans2.json")
        exporter.export_spans([Span(name="span-1")])
        exporter.export_spans([Span(name="span-2")])
        data = (tmp_path / "spans2.json").read_text()
        assert "span-1" in data
        assert "span-2" in data


# ---------------------------------------------------------------------------
# AgentTracer
# ---------------------------------------------------------------------------

class TestAgentTracer:
    def test_create_tracer(self, tmp_path: Path):
        tracer = AgentTracer(trace_dir=tmp_path / "traces", enable_otel_sdk=False)
        assert tracer.buffer.span_count == 0

    def test_span_context_manager(self, tmp_path: Path):
        tracer = AgentTracer(trace_dir=tmp_path / "traces2", enable_otel_sdk=False)
        with tracer.span("my-op", {"key": "value"}) as span:
            assert span.name == "my-op"
            assert span.attributes["key"] == "value"
            assert span.status == "unset"
        # After exiting, span should be recorded
        assert tracer.buffer.span_count == 1
        recorded = tracer.buffer.get_recent(1)[0]
        assert recorded.status == "ok"

    def test_span_error_status(self, tmp_path: Path):
        tracer = AgentTracer(trace_dir=tmp_path / "traces3", enable_otel_sdk=False)
        try:
            with tracer.span("failing-op"):
                raise ValueError("test error")
        except ValueError:
            pass
        assert tracer.buffer.span_count == 1
        span = tracer.buffer.get_recent(1)[0]
        assert span.status == "error"
        assert span.attributes.get("error.type") == "ValueError"

    def test_dashboard(self, tmp_path: Path):
        tracer = AgentTracer(trace_dir=tmp_path / "traces4", enable_otel_sdk=False)
        with tracer.span("op1"):
            pass
        dash = tracer.get_dashboard()
        assert dash["total_spans"] >= 1

    def test_export_all(self, tmp_path: Path):
        tracer = AgentTracer(trace_dir=tmp_path / "traces5", enable_otel_sdk=False)
        with tracer.span("export-me"):
            pass
        tracer.export_all()
        assert (tmp_path / "traces5" / "spans.json").exists()

    def test_consistent_trace_id(self, tmp_path: Path):
        tracer = AgentTracer(trace_dir=tmp_path / "traces6", enable_otel_sdk=False)
        with tracer.span("op-a"):
            pass
        with tracer.span("op-b"):
            pass
        spans = tracer.buffer.get_recent(2)
        assert spans[0].trace_id == spans[1].trace_id

    def test_no_trace_dir(self):
        tracer = AgentTracer(enable_otel_sdk=False)
        with tracer.span("no-dir-op"):
            pass
        # Should not crash
        assert tracer.buffer.span_count == 1


# ---------------------------------------------------------------------------
# React tracer helpers
# ---------------------------------------------------------------------------

class TestReactTracerHelpers:
    def test_trace_llm_call_decorator(self, tmp_path: Path):
        tracer = AgentTracer(trace_dir=tmp_path / "traces7", enable_otel_sdk=False)
        helpers = _ReactTracerHelpers(tracer)

        @helpers.trace_llm_call
        def fake_llm_call():
            return ("response text", (100, 50))

        result = fake_llm_call()
        assert result == ("response text", (100, 50))
        assert tracer.buffer.span_count >= 1

    def test_trace_tool_execution_decorator(self, tmp_path: Path):
        tracer = AgentTracer(trace_dir=tmp_path / "traces8", enable_otel_sdk=False)
        helpers = _ReactTracerHelpers(tracer)

        @helpers.trace_tool_execution("read_file")
        def fake_tool(file_path):
            return f"Content of {file_path}"

        result = fake_tool("test.py")
        assert "test.py" in result
        assert tracer.buffer.span_count >= 1

    def test_create_react_tracer(self, tmp_path: Path):
        tracer = AgentTracer(trace_dir=tmp_path / "traces9", enable_otel_sdk=False)
        helpers = create_react_tracer(tracer)
        assert helpers is not None

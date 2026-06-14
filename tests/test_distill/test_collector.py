"""Unit tests for TraceCollector."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from my_code_agent.distill.collector import TraceCollector
from my_code_agent.distill.models import SessionTrace, TraceStep


class TestTraceCollectorBegin:
    def test_begin_session_returns_id(self, tmp_path: Path) -> None:
        tc = TraceCollector(tmp_path)
        tid = tc.begin_session("refactor auth module")
        assert tid.startswith("trace_")
        assert isinstance(int(tid[6:]), int)  # timestamp-based

    def test_begin_session_creates_current_trace(self, tmp_path: Path) -> None:
        tc = TraceCollector(tmp_path)
        tc.begin_session("test input")
        assert tc._current_trace is not None
        assert tc._current_trace.user_input == "test input"


class TestTraceCollectorRecord:
    def test_record_appends_step(self, tmp_path: Path) -> None:
        tc = TraceCollector(tmp_path)
        tc.begin_session("test")
        tc.record_step(
            TraceStep(step_number=1, thought="thinking"),
            prompt_tokens=100,
            completion_tokens=50,
            cost=0.001,
        )
        assert len(tc._current_trace.steps) == 1
        step = tc._current_trace.steps[0]
        assert step.step_number == 1
        assert step.prompt_tokens == 100
        assert step.cost == 0.001

    def test_record_without_begin_is_safe(self, tmp_path: Path) -> None:
        tc = TraceCollector(tmp_path)
        # Should not raise
        tc.record_step(TraceStep(step_number=1))


class TestTraceCollectorFinishAndPersist:
    def test_finish_persists_to_jsonl(self, tmp_path: Path) -> None:
        tc = TraceCollector(tmp_path, trace_dir=tmp_path / "traces")
        tc.begin_session("refactor function")
        tc.record_step(
            TraceStep(step_number=1, thought="read"),
            prompt_tokens=50,
            completion_tokens=25,
            cost=0.0005,
        )
        tc.record_step(
            TraceStep(step_number=2, thought="replace"),
            prompt_tokens=50,
            completion_tokens=25,
            cost=0.0005,
        )
        tc.finish_session("Refactored successfully.", success=True)

        # Verify file was written
        trace_files = list((tmp_path / "traces").rglob("*.jsonl"))
        assert len(trace_files) == 1

        content = trace_files[0].read_text(encoding="utf-8")
        lines = content.strip().split("\n")

        # Should have 2 step lines + 1 summary line
        assert len(lines) == 3

        # Verify step lines
        step1 = json.loads(lines[0])
        assert step1["step_number"] == 1
        assert step1["action"] is None
        assert step1["prompt_tokens"] == 50

        # Verify summary line
        summary = json.loads(lines[-1])
        assert summary["trace_id"].startswith("trace_")
        assert summary["success"] is True
        assert summary["step_count"] == 2
        assert "refactor" in summary["user_input"]

    def test_finish_marks_failure(self, tmp_path: Path) -> None:
        tc = TraceCollector(tmp_path, trace_dir=tmp_path / "traces")
        tc.begin_session("do something")
        tc.finish_session("Error occurred.", success=False)

        trace_files = list((tmp_path / "traces").rglob("*.jsonl"))
        summary = json.loads(trace_files[0].read_text().strip().split("\n")[-1])
        assert summary["success"] is False


class TestTraceCollectorLoad:
    def test_get_successful_traces(self, tmp_path: Path) -> None:
        tc = TraceCollector(tmp_path, trace_dir=tmp_path / "traces")

        # Write a successful trace manually
        tc.begin_session("test 1")
        tc.record_step(TraceStep(step_number=1))
        tc.finish_session("done", success=True)

        traces = tc.get_successful_traces()
        assert len(traces) == 1
        assert traces[0].success is True
        assert traces[0].user_input == "test 1"

    def test_get_successful_filters_failures(self, tmp_path: Path) -> None:
        tc = TraceCollector(tmp_path, trace_dir=tmp_path / "traces")

        # Write mixed traces
        tc.begin_session("ok")
        tc.finish_session("done", success=True)

        tc.begin_session("fail")
        tc.finish_session("error", success=False)

        successful = tc.get_successful_traces()
        assert len(successful) == 1
        assert successful[0].user_input == "ok"

    def test_get_recent_traces(self, tmp_path: Path) -> None:
        tc = TraceCollector(tmp_path, trace_dir=tmp_path / "traces")
        tc.begin_session("recent")
        tc.finish_session("done", success=True)
        recent = tc.get_recent_traces(hours=24)
        assert len(recent) == 1

    def test_get_from_empty_dir(self, tmp_path: Path) -> None:
        tc = TraceCollector(tmp_path, trace_dir=tmp_path / "nonexistent")
        assert tc.get_successful_traces() == []
        assert tc.get_recent_traces() == []

    def test_roundtrip(self, tmp_path: Path) -> None:
        tc = TraceCollector(tmp_path, trace_dir=tmp_path / "traces")
        tc.begin_session("roundtrip test")
        tc.record_step(
            TraceStep(
                step_number=1,
                thought="read file",
                action="read_file",
                action_input={"file_path": "main.py"},
                observation="# hello\nworld",
            ),
            prompt_tokens=200,
            completion_tokens=100,
            cost=0.002,
        )
        tc.finish_session("File read successfully.", success=True)

        # Load via a new collector instance
        tc2 = TraceCollector(tmp_path, trace_dir=tmp_path / "traces")
        traces = tc2.get_successful_traces()
        assert len(traces) == 1
        t = traces[0]
        assert t.trace_id is not None
        assert len(t.steps) == 1
        assert t.steps[0].action == "read_file"
        assert t.steps[0].observation == "# hello\nworld"
        assert t.steps[0].prompt_tokens == 200

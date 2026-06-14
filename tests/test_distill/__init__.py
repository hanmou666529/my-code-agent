"""Unit tests for distill package __init__ exports."""

from __future__ import annotations

from my_code_agent.distill import (
    DraftStatus,
    EvalResult,
    PipelineReport,
    SessionTrace,
    SkillDraft,
    TraceCluster,
    TraceCollector,
    TraceStep,
)


class TestExports:
    """Verify that __init__.py exports all expected symbols."""

    def test_models_exported(self) -> None:
        assert DraftStatus is not None
        assert EvalResult is not None
        assert PipelineReport is not None
        assert SessionTrace is not None
        assert SkillDraft is not None
        assert TraceCluster is not None
        assert TraceStep is not None

    def test_collector_exported(self) -> None:
        assert TraceCollector is not None

    def test_create_trace_step(self) -> None:
        step = TraceStep(step_number=1, thought="test")
        assert step.step_number == 1

    def test_create_session_trace(self) -> None:
        trace = SessionTrace(trace_id="t1", user_input="hi")
        assert trace.trace_id == "t1"

    def test_create_collector(self, tmp_path) -> None:
        tc = TraceCollector(tmp_path)
        assert tc is not None

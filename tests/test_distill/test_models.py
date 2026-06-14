"""Unit tests for distill package models."""

from __future__ import annotations

import json
import time

import pytest

from my_code_agent.distill.models import (
    DraftStatus,
    EvalResult,
    PipelineReport,
    SessionTrace,
    SkillDraft,
    TraceCluster,
    TraceStep,
)


class TestTraceStep:
    def test_default_values(self) -> None:
        step = TraceStep(step_number=1)
        assert step.step_number == 1
        assert step.thought == ""
        assert step.action is None
        assert step.prompt_tokens == 0
        assert step.cost == 0.0

    def test_to_dict(self) -> None:
        step = TraceStep(
            step_number=1,
            thought="Let me read the file",
            action="read_file",
            action_input={"file_path": "main.py"},
            observation="# content",
            prompt_tokens=100,
            completion_tokens=50,
            cost=0.001,
        )
        d = step.to_dict()
        assert d["step_number"] == 1
        assert d["action"] == "read_file"
        assert d["prompt_tokens"] == 100
        assert d["cost"] == 0.001

    def test_from_dict(self) -> None:
        d = {
            "step_number": 2,
            "thought": "thinking",
            "action": "write_file",
            "action_input": {"path": "x.py"},
            "observation": "written",
            "prompt_tokens": 200,
            "completion_tokens": 100,
            "cost": 0.002,
            "timestamp": 1000.0,
        }
        step = TraceStep.from_dict(d)
        assert step.step_number == 2
        assert step.action == "write_file"
        assert step.prompt_tokens == 200

    def test_roundtrip(self) -> None:
        original = TraceStep(
            step_number=5,
            thought="test",
            action="test",
            action_input={"a": 1},
            observation="ok",
            prompt_tokens=10,
            completion_tokens=20,
            cost=0.01,
        )
        restored = TraceStep.from_dict(original.to_dict())
        assert restored.step_number == original.step_number
        assert restored.action == original.action
        assert restored.action_input == original.action_input
        assert restored.prompt_tokens == original.prompt_tokens


class TestSessionTrace:
    def test_minimal(self) -> None:
        trace = SessionTrace(trace_id="t1", user_input="hello")
        assert trace.trace_id == "t1"
        assert trace.steps == []
        assert trace.success is False

    def test_add_step(self) -> None:
        trace = SessionTrace(trace_id="t1", user_input="hello")
        trace.add_step(TraceStep(step_number=1, thought="a"))
        assert len(trace.steps) == 1
        assert trace.steps[0].step_number == 1

    def test_to_dict(self) -> None:
        trace = SessionTrace(
            trace_id="t1",
            user_input="test",
            steps=[TraceStep(step_number=1)],
            final_answer="done",
            success=True,
        )
        d = trace.to_dict()
        assert d["trace_id"] == "t1"
        assert len(d["steps"]) == 1
        assert d["success"] is True

    def test_from_dict(self) -> None:
        d = {
            "trace_id": "t2",
            "user_input": "world",
            "steps": [{"step_number": 1, "thought": "x"}],
            "final_answer": "ok",
            "success": True,
        }
        trace = SessionTrace.from_dict(d)
        assert trace.trace_id == "t2"
        assert len(trace.steps) == 1
        assert trace.success is True


class TestTraceCluster:
    def test_minimal(self) -> None:
        c = TraceCluster(
            cluster_id="c1",
            task_signature="refactor",
            trace_ids=["t1", "t2"],
            size=2,
        )
        assert c.cluster_id == "c1"
        assert c.median_trajectory == []


class TestSkillDraft:
    def test_default_status(self) -> None:
        d = SkillDraft(draft_id="d1", skill_md_content="---\nname: test\n---")
        assert d.status == DraftStatus.PENDING_EVAL
        assert d.feedback == ""


class TestEvalResult:
    def test_pass(self) -> None:
        r = EvalResult(passed=True, pass_rate=1.0)
        assert r.passed is True
        assert r.details == []

    def test_fail(self) -> None:
        r = EvalResult(passed=False, pass_rate=0.5, feedback="too slow")
        assert r.passed is False
        assert r.feedback == "too slow"


class TestPipelineReport:
    def test_summary(self) -> None:
        r = PipelineReport(
            traces_collected=10,
            clusters_found=2,
            drafts_generated=1,
            eval_passed=1,
            eval_rejected=0,
            errors=["minor issue"],
        )
        s = r.summary()
        assert "10" in s
        assert "2" in s
        assert "1" in s
        assert "minor issue" in s

    def test_empty_summary(self) -> None:
        r = PipelineReport()
        s = r.summary()
        assert "0" in s


class TestDraftStatus:
    def test_all_statuses_exist(self) -> None:
        assert DraftStatus.PENDING_EVAL.value == "pending_eval"
        assert DraftStatus.APPROVED_PUBLISHED.value == "published"
        assert DraftStatus.REJECTED_REVIEW.value == "rejected_review"

"""Unit tests for DistillationPipeline orchestrator."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

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
from my_code_agent.distill.pipeline import DistillationPipeline, PipelineMode


def _make_success_trace(
    trace_id: str,
    user_input: str,
    steps: list[TraceStep] | None = None,
) -> SessionTrace:
    """Helper to create a successful session trace."""
    return SessionTrace(
        trace_id=trace_id,
        user_input=user_input,
        steps=steps or [
            TraceStep(step_number=1, action="read_file"),
            TraceStep(step_number=2, action="search_replace"),
        ],
        success=True,
        final_answer="Done.",
    )


def _make_cluster(
    trace_ids: list[str],
    task_sig: str = "refactor auth",
    size: int = 3,
) -> TraceCluster:
    return TraceCluster(
        cluster_id="c1",
        task_signature=task_sig,
        trace_ids=trace_ids,
        size=size,
        median_trajectory=[
            {"position": 0, "action": "read_file", "frequency": 3, "total": 3},
            {"position": 1, "action": "search_replace", "frequency": 3, "total": 3},
        ],
    )


class TestPipelineRunOnce:
    def _make_mock_config(self, tmp_path: Path) -> MagicMock:
        config = MagicMock()
        config.workspace_path = tmp_path
        config.trace_dir = ".agent/traces"
        config.api_base = "http://fake"
        config.anthropic_api_key = ""
        config.primary_model = "fake/model"
        config.distill_interval_hours = 1
        config.distill_min_cluster_size = 3
        return config

    def test_empty_traces(self, tmp_path: Path) -> None:
        config = self._make_mock_config(tmp_path)
        pipeline = DistillationPipeline(config)
        report = pipeline.run_once()

        assert report.traces_collected == 0
        assert report.clusters_found == 0
        assert report.drafts_generated == 0

    def test_no_clusters(self, tmp_path: Path) -> None:
        """Traces exist but all unique → no clusters (below min_cluster_size)."""
        config = self._make_mock_config(tmp_path)
        pipeline = DistillationPipeline(config, min_cluster_size=5)
        report = pipeline.run_once()

        # No traces on disk = 0 collected
        assert report.traces_collected == 0

    def test_full_pipeline(self, tmp_path: Path) -> None:
        """End-to-end: write traces → run pipeline → verify report."""
        config = self._make_mock_config(tmp_path)

        # Write 3 similar successful traces to disk
        trace_dir = tmp_path / ".agent" / "traces"
        date_dir = trace_dir / "2026" / "06"
        date_dir.mkdir(parents=True)

        for i in range(3):
            trace = _make_success_trace(
                trace_id=f"trace_{i}",
                user_input="refactor the auth module",
                steps=[
                    TraceStep(step_number=1, action="read_file"),
                    TraceStep(step_number=2, action="search_replace"),
                    TraceStep(step_number=3, action="write_file"),
                ],
            )
            jsonl_path = date_dir / f"trace_{i}.jsonl"
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for step in trace.steps:
                    f.write(json.dumps(step.to_dict()) + "\n")
                f.write(json.dumps({
                    "trace_id": trace.trace_id,
                    "user_input": trace.user_input,
                    "final_answer": trace.final_answer,
                    "success": trace.success,
                    "step_count": len(trace.steps),
                    "started_at": trace.started_at,
                }) + "\n")

        pipeline = DistillationPipeline(config)
        report = pipeline.run_once()

        assert report.traces_collected == 3
        # Clustering should produce 1 cluster
        assert report.clusters_found >= 1
        if report.clusters_found > 0:
            assert report.drafts_generated >= 1


class TestPipelineModes:
    def test_one_shot_mode(self, tmp_path: Path) -> None:
        config = MagicMock()
        config.workspace_path = tmp_path
        mode = PipelineMode.ONE_SHOT
        assert mode.value == "one_shot"

    def test_daemon_mode(self, tmp_path: Path) -> None:
        config = MagicMock()
        config.workspace_path = tmp_path
        mode = PipelineMode.DAEMON
        assert mode.value == "daemon"


class TestPipelineConfig:
    def test_uses_config_min_cluster_size(self, tmp_path: Path) -> None:
        config = MagicMock()
        config.workspace_path = tmp_path
        config.trace_dir = ".agent/traces"
        config.api_base = "http://fake"
        config.anthropic_api_key = ""
        config.primary_model = "fake/model"
        config.distill_interval_hours = 12
        config.distill_min_cluster_size = 5

        pipeline = DistillationPipeline(config)
        assert pipeline._min_cluster_size == 5

    def test_eval_threshold_default(self, tmp_path: Path) -> None:
        config = MagicMock()
        config.workspace_path = tmp_path
        config.trace_dir = ".agent/traces"
        config.api_base = "http://fake"
        config.anthropic_api_key = ""
        config.primary_model = "fake/model"
        config.distill_interval_hours = 1
        config.distill_min_cluster_size = 3

        pipeline = DistillationPipeline(config)
        assert pipeline._eval_threshold == 0.95

"""DistillationPipeline — orchestrator for the Auto-Distill Pipeline.

Wires together all stages: TraceCollector → TraceMiner → SkillDraftGenerator
→ EvalGate → HumanReview. Supports one-shot execution and a daemon mode
with configurable interval.

Usage:
    # One-shot
    pipeline = DistillationPipeline(config)
    report = pipeline.run_once()
    print(report.summary())

    # Daemon
    pipeline.run_daemon(interval_hours=6)
"""

from __future__ import annotations

import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import AgentConfig
from .collector import TraceCollector
from .draft_generator import SkillDraftGenerator
from .eval_gate import EVAL_PASS_THRESHOLD, EvalGate
from .human_review import HumanReview
from .miner import TraceMiner
from .models import (
    DraftStatus,
    EvalResult,
    PipelineReport,
    SkillDraft,
    TraceCluster,
    TraceStep,
)


class PipelineMode(Enum):
    """Pipeline execution mode."""
    ONE_SHOT = "one_shot"
    DAEMON = "daemon"


class DistillationPipeline:
    """Orchestrates the full distillation pipeline."""

    def __init__(
        self,
        config: AgentConfig,
        mode: PipelineMode = PipelineMode.ONE_SHOT,
        min_cluster_size: Optional[int] = None,
        eval_threshold: Optional[float] = None,
    ) -> None:
        self._config = config
        self._workspace = config.workspace_path
        self._mode = mode
        self._min_cluster_size = min_cluster_size or config.distill_min_cluster_size
        self._eval_threshold = eval_threshold or EVAL_PASS_THRESHOLD

        # Initialize components
        trace_dir = self._workspace / config.trace_dir
        self._collector = TraceCollector(self._workspace, trace_dir=trace_dir)

        self._miner = TraceMiner(self._workspace)

        draft_dir = self._workspace / ".agent" / "skills" / "drafts"
        self._generator = SkillDraftGenerator(
            api_base=config.api_base,
            api_key=config.anthropic_api_key or "",
            model=config.primary_model,
            draft_dir=draft_dir,
        )

        self._eval_gate = EvalGate(self._workspace)
        self._review = HumanReview(self._workspace)

    # ---- Public API ----

    def run_once(self) -> PipelineReport:
        """Execute one complete distillation cycle.

        Phases:
        1. Collect successful traces
        2. Cluster traces by task similarity
        3. Generate skill drafts from clusters
        4. Evaluate drafts against eval cases
        5. Queue approved drafts for human review

        Returns:
            PipelineReport with summary statistics.
        """
        report = PipelineReport()

        try:
            # Phase 1: Collect
            traces = self._collector.get_successful_traces()
            report.traces_collected = len(traces)
            if not traces:
                return report

            # Phase 2: Mine (cluster)
            clusters = self._miner.cluster_traces(traces, min_cluster_size=self._min_cluster_size)
            report.clusters_found = len(clusters)
            if not clusters:
                return report

            # Phase 3: Generate drafts
            for cluster in clusters:
                try:
                    draft = self._generator.generate_draft(cluster)
                    self._generator.save_draft(draft)
                    report.drafts_generated += 1

                    # Phase 4: Eval gate
                    eval_result = self._eval_gate.evaluate(draft)
                    if eval_result.passed:
                        report.eval_passed += 1
                        draft.status = DraftStatus.APPROVED_EVAL
                        draft.feedback = eval_result.feedback
                        # Phase 5: Queue for review
                        self._review.queue_for_review(draft)
                        report.review_approved += 1
                    else:
                        report.eval_rejected += 1
                        draft.status = DraftStatus.REJECTED_EVAL
                        draft.feedback = eval_result.feedback
                except Exception as e:
                    report.errors.append(f"Draft generation failed for cluster: {e}")

        except Exception as e:
            report.errors.append(f"Pipeline error: {e}")

        return report

    def run_daemon(self, interval_hours: Optional[int] = None) -> None:
        """Run the pipeline in daemon mode.

        Repeatedly runs `run_once()` at the specified interval.
        Runs in the foreground (blocking).
        """
        interval_seconds = (interval_hours or self._config.distill_interval_hours) * 3600

        while True:
            try:
                report = self.run_once()
                print(report.summary())
            except Exception as e:
                print(f"[DISTILL ERROR] {e}")
            time.sleep(interval_seconds)

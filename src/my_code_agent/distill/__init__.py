"""Auto-Distill Pipeline — self-evolving skill generation system.

Transforms successful user session traces into new Executable Skills through
4 stages: Trace Miner → Skill Draft Generator → Eval Gate → Human Review.
"""

from __future__ import annotations

from .models import (
    DraftStatus,
    EvalResult,
    PipelineReport,
    SessionTrace,
    SkillDraft,
    TraceCluster,
    TraceStep,
)
from .collector import TraceCollector
from .miner import TraceMiner
from .draft_generator import SkillDraftGenerator
from .eval_gate import EvalGate, EVAL_PASS_THRESHOLD
from .human_review import HumanReview
from .pipeline import DistillationPipeline, PipelineMode

__all__ = [
    # Models
    "DraftStatus",
    "EvalResult",
    "PipelineReport",
    "SessionTrace",
    "SkillDraft",
    "TraceCluster",
    "TraceStep",
    # Components
    "TraceCollector",
    "TraceMiner",
    "SkillDraftGenerator",
    "EvalGate",
    "EVAL_PASS_THRESHOLD",
    "HumanReview",
    # Pipeline
    "DistillationPipeline",
    "PipelineMode",
]

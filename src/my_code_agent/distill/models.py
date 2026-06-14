"""Auto-Distill Pipeline data models.

Defines the data structures for the distillation pipeline:
trace steps, session traces, clusters, skill drafts, eval results,
and pipeline reports.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class DraftStatus(Enum):
    """Lifecycle status of a skill draft."""

    PENDING_EVAL = "pending_eval"
    APPROVED_EVAL = "approved_eval"
    REJECTED_EVAL = "rejected_eval"
    PENDING_REVIEW = "pending_review"
    APPROVED_PUBLISHED = "published"
    REJECTED_REVIEW = "rejected_review"


@dataclass
class TraceStep:
    """One persisted step from a ReAct session."""

    step_number: int
    thought: str = ""
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None
    error: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "step_number": self.step_number,
            "thought": self.thought,
            "action": self.action,
            "action_input": self.action_input,
            "observation": self.observation,
            "error": self.error,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost": self.cost,
            "timestamp": self.timestamp,
        }
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TraceStep":
        return cls(
            step_number=d["step_number"],
            thought=d.get("thought", ""),
            action=d.get("action"),
            action_input=d.get("action_input"),
            observation=d.get("observation"),
            error=d.get("error"),
            prompt_tokens=d.get("prompt_tokens", 0),
            completion_tokens=d.get("completion_tokens", 0),
            cost=d.get("cost", 0.0),
            timestamp=d.get("timestamp", time.time()),
        )


@dataclass
class SessionTrace:
    """A complete user session: one request + all ReAct steps."""

    trace_id: str
    user_input: str
    steps: list[TraceStep] = field(default_factory=list)
    final_answer: str = ""
    success: bool = False
    workspace_snapshot: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def add_step(self, step: TraceStep) -> None:
        self.steps.append(step)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "user_input": self.user_input,
            "steps": [s.to_dict() for s in self.steps],
            "final_answer": self.final_answer,
            "success": self.success,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SessionTrace":
        return cls(
            trace_id=d["trace_id"],
            user_input=d["user_input"],
            steps=[TraceStep.from_dict(s) for s in d.get("steps", [])],
            final_answer=d.get("final_answer", ""),
            success=d.get("success", False),
            workspace_snapshot=d.get("workspace_snapshot"),
            started_at=d.get("started_at", time.time()),
            completed_at=d.get("completed_at"),
        )


@dataclass
class TraceCluster:
    """Group of similar successful traces."""

    cluster_id: str
    task_signature: str
    trace_ids: list[str]
    median_trajectory: list[dict] = field(default_factory=list)
    size: int = 0


@dataclass
class SkillDraft:
    """A candidate skill produced by the draft generator."""

    draft_id: str
    skill_md_content: str
    status: DraftStatus = DraftStatus.PENDING_EVAL
    feedback: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class EvalResult:
    """Result of evaluating a drafted skill."""

    passed: bool
    pass_rate: float
    details: list[dict] = field(default_factory=list)
    feedback: str = ""


@dataclass
class PipelineReport:
    """Summary of a distillation pipeline run."""

    traces_collected: int = 0
    clusters_found: int = 0
    drafts_generated: int = 0
    eval_passed: int = 0
    eval_rejected: int = 0
    review_approved: int = 0
    review_rejected: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Return a human-readable report string."""
        lines = [
            "Distillation Pipeline Report",
            "=" * 40,
            f"Traces collected: {self.traces_collected}",
            f"Clusters found:   {self.clusters_found}",
            f"Drafts generated: {self.drafts_generated}",
            f"Eval passed:      {self.eval_passed}",
            f"Eval rejected:    {self.eval_rejected}",
            f"Review approved:  {self.review_approved}",
            f"Review rejected:  {self.review_rejected}",
        ]
        if self.errors:
            lines.append("Errors:")
            for e in self.errors:
                lines.append(f"  - {e}")
        return "\n".join(lines)

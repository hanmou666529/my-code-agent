"""TraceCollector — captures ReAct steps into persistent JSONL traces.

Persists traces to ``.agent/traces/YYYY/MM/<trace_id>.jsonl`` — one file
per session, one line per ``TraceStep``, last line is a session summary
with the ``success`` flag for easy filtering.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import SessionTrace, TraceStep


class TraceCollector:
    """Collects ReAct steps and persists them as JSONL traces."""

    def __init__(
        self,
        workspace_root: Path,
        trace_dir: Optional[Path] = None,
    ) -> None:
        self._workspace = workspace_root.resolve()
        self._trace_dir = (trace_dir or self._workspace / ".agent" / "traces").resolve()
        self._current_trace: Optional[SessionTrace] = None

    # ---- Public API ----

    def begin_session(self, user_input: str) -> str:
        """Start recording a new session.

        Returns the trace_id (a simple timestamp-based ID).
        """
        trace_id = f"trace_{int(time.time() * 1000)}"
        self._current_trace = SessionTrace(
            trace_id=trace_id,
            user_input=user_input,
        )
        return trace_id

    def record_step(
        self,
        step: TraceStep,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost: float = 0.0,
    ) -> None:
        """Record a single ReAct step with token/cost metadata."""
        if self._current_trace is None:
            return
        step.prompt_tokens = prompt_tokens
        step.completion_tokens = completion_tokens
        step.cost = cost
        self._current_trace.add_step(step)

    def finish_session(self, final_answer: str, success: bool) -> None:
        """Finish the current session and persist to disk.

        Args:
            final_answer: The agent's final response.
            success: Whether the session was deemed successful.
        """
        if self._current_trace is None:
            return
        self._current_trace.final_answer = final_answer
        self._current_trace.success = success
        self._current_trace.completed_at = time.time()
        self._persist(self._current_trace)
        self._current_trace = None

    def get_successful_traces(self) -> list[SessionTrace]:
        """Load all successful traces from disk."""
        return self._load_traces(success_only=True)

    def get_recent_traces(self, hours: int = 24) -> list[SessionTrace]:
        """Load traces from the last N hours (any outcome)."""
        cutoff = time.time() - (hours * 3600)
        return self._load_traces(success_only=False, after_timestamp=cutoff)

    # ---- Internal ----

    def _persist(self, trace: SessionTrace) -> None:
        """Write a session trace to JSONL on disk."""
        # Date-based directory structure
        t = time.localtime(trace.started_at)
        date_dir = self._trace_dir / str(t.tm_year) / f"{t.tm_mon:02d}"
        date_dir.mkdir(parents=True, exist_ok=True)

        file_path = date_dir / f"{trace.trace_id}.jsonl"

        with open(file_path, "a", encoding="utf-8") as f:
            for step in trace.steps:
                f.write(json.dumps(step.to_dict(), ensure_ascii=False) + "\n")
            # Last line: session summary with success flag
            summary = {
                "trace_id": trace.trace_id,
                "user_input": trace.user_input,
                "final_answer": trace.final_answer,
                "success": trace.success,
                "step_count": len(trace.steps),
                "started_at": trace.started_at,
                "completed_at": trace.completed_at,
            }
            f.write(json.dumps(summary, ensure_ascii=False) + "\n")

    def _load_traces(
        self,
        success_only: bool = False,
        after_timestamp: Optional[float] = None,
    ) -> list[SessionTrace]:
        """Load SessionTrace objects from JSONL files."""
        if not self._trace_dir.exists():
            return []

        traces: list[SessionTrace] = []

        for jsonl_path in sorted(self._trace_dir.rglob("*.jsonl")):
            try:
                lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
            except (OSError, UnicodeDecodeError):
                continue

            if not lines:
                continue

            # Parse steps (all lines except the last)
            steps: list[TraceStep] = []
            summary_line = lines[-1]
            try:
                summary: Dict[str, Any] = json.loads(summary_line)
            except json.JSONDecodeError:
                continue

            for line in lines[:-1]:
                line = line.strip()
                if not line:
                    continue
                try:
                    step_data = json.loads(line)
                    steps.append(TraceStep.from_dict(step_data))
                except (json.JSONDecodeError, KeyError):
                    continue

            # Filter by success and timestamp
            if success_only and not summary.get("success", False):
                continue
            if after_timestamp is not None:
                started = summary.get("started_at", 0)
                if started < after_timestamp:
                    continue

            trace = SessionTrace(
                trace_id=summary["trace_id"],
                user_input=summary["user_input"],
                steps=steps,
                final_answer=summary.get("final_answer", ""),
                success=summary.get("success", False),
                started_at=summary.get("started_at", time.time()),
                completed_at=summary.get("completed_at"),
            )
            traces.append(trace)

        return traces

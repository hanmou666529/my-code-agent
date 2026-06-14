"""Dependency Engine v2 — graph analysis, failure tracking, usage analytics, and auto-deprecation.

Provides the Workspace Intelligence Layer with:
- Dependency graph engine with blast radius / critical module detection
- Failure trace recording and improvement suggestion generation
- Usage analytics for tool hotspots, slow tools, underused tools
- Auto-deprecation scanning for stale modules
"""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# CircularDependencyError
# ---------------------------------------------------------------------------


class CircularDependencyError(Exception):
    """Raised when a circular dependency is detected in the graph."""


# ---------------------------------------------------------------------------
# FailureTracker
# ---------------------------------------------------------------------------


@dataclass
class FailureRecord:
    """A single recorded failure trace."""

    tool_name: str
    error: str
    file_path: Optional[str] = None
    module: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    stack_summary: str = ""


class FailureTracker:
    """Record tool failures, correlate with dependency graph, suggest improvements."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace = workspace_root.resolve()
        self._store_path = self._workspace / ".agent" / "failures.json"
        self._records: list[FailureRecord] = []
        self._load()

    def record_failure(
        self,
        tool_name: str,
        error: str,
        file_path: Optional[str] = None,
        module: Optional[str] = None,
        stack_summary: str = "",
    ) -> None:
        """Record a tool execution failure."""
        record = FailureRecord(
            tool_name=tool_name,
            error=error,
            file_path=file_path,
            module=module,
            stack_summary=stack_summary,
        )
        self._records.append(record)
        self._save()

    def get_failure_report(self) -> str:
        """Get a summary of recent failures."""
        if not self._records:
            return "No recorded failures."

        total = len(self._records)
        by_tool: Counter = Counter()
        by_module: Counter = Counter()

        for r in self._records:
            by_tool[r.tool_name] += 1
            if r.module:
                by_module[r.module] += 1

        lines = [f"Failure Report: {total} total failure(s)"]
        lines.append("By tool:")
        for tool, count in by_tool.most_common():
            lines.append(f"  {tool}: {count}")
        lines.append("By module:")
        for mod, count in by_module.most_common():
            lines.append(f"  {mod}: {count}")

        # Recent errors
        lines.append("Recent errors:")
        for r in self._records[-5:]:
            lines.append(f"  [{r.tool_name}] {r.error[:100]}")

        return "\n".join(lines)

    def get_improvement_suggestions(self) -> list[str]:
        """Generate improvement suggestions based on failure patterns."""
        suggestions: list[str] = []
        if not self._records:
            return suggestions

        # Pattern 1: Many failures in same tool → suggest validation
        by_tool: Counter = Counter(r.tool_name for r in self._records)
        for tool, count in by_tool.most_common(3):
            if count >= 3:
                suggestions.append(
                    f"High failure rate on ``{tool}`` ({count} failures). "
                    "Consider adding better input validation or fallback logic."
                )

        # Pattern 2: Failures clustering around a module → suggest module review
        by_module: Counter = Counter(
            r.module for r in self._records if r.module
        )
        for mod, count in by_module.most_common(3):
            if count >= 2:
                suggestions.append(
                    f"Module ``{mod}`` has {count} failure(s). "
                    "Consider adding integration tests or review module boundaries."
                )

        # Pattern 3: Path traversal errors → suggest path normalization
        path_errors = [
            r for r in self._records if "path" in r.error.lower()
            or "traversal" in r.error.lower() or "escapes" in r.error.lower()
        ]
        if len(path_errors) >= 2:
            suggestions.append(
                "Multiple path-related failures detected. "
                "Consider adding path normalization and canonical resolution."
            )

        return suggestions

    def get_failed_modules(self) -> set[str]:
        """Return set of module names with recorded failures."""
        return {
            r.module for r in self._records
            if r.module
        }

    def _save(self) -> None:
        """Persist failure records to JSON."""
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "tool_name": r.tool_name,
                "error": r.error,
                "file_path": r.file_path,
                "module": r.module,
                "timestamp": r.timestamp,
                "stack_summary": r.stack_summary,
            }
            for r in self._records
        ]
        self._store_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        """Load failure records from JSON."""
        if not self._store_path.exists():
            return
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
            for item in data:
                self._records.append(FailureRecord(**item))
        except (json.JSONDecodeError, OSError, TypeError):
            self._records = []


# ---------------------------------------------------------------------------
# UsageAnalytics
# ---------------------------------------------------------------------------


@dataclass
class CallRecord:
    """A single tool call record."""

    tool_name: str
    success: bool
    duration_ms: float
    timestamp: float = field(default_factory=time.time)


class UsageAnalytics:
    """Track tool usage, identify hotspots, slow tools, and underused tools."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace = workspace_root.resolve()
        self._store_path = self._workspace / ".agent" / "usage.json"
        self._records: list[CallRecord] = []
        self._load()

    def record_call(self, tool_name: str, success: bool, duration_ms: float) -> None:
        """Record a tool call."""
        self._records.append(CallRecord(
            tool_name=tool_name, success=success, duration_ms=duration_ms,
        ))
        self._save()

    def get_hotspots(self, top_n: int = 10) -> list[dict]:
        """Find most frequently called tools."""
        counts: Counter = Counter(r.tool_name for r in self._records)
        return [
            {"tool": tool, "calls": count}
            for tool, count in counts.most_common(top_n)
        ]

    def get_slow_tools(self, min_calls: int = 5) -> list[dict]:
        """Find tools with highest average duration (minimum call threshold)."""
        durations: dict[str, list[float]] = defaultdict(list)
        for r in self._records:
            durations[r.tool_name].append(r.duration_ms)

        results = []
        for tool, durs in durations.items():
            if len(durs) >= min_calls:
                avg = sum(durs) / len(durs)
                results.append({
                    "tool": tool,
                    "avg_duration_ms": round(avg, 1),
                    "calls": len(durs),
                })
        return sorted(results, key=lambda x: x["avg_duration_ms"], reverse=True)

    def get_underused_tools(self, max_calls: int = 2) -> list[dict]:
        """Find tools called very rarely."""
        counts: Counter = Counter(r.tool_name for r in self._records)
        all_tools = set(counts.keys())
        underused = [
            {"tool": tool, "calls": counts[tool]}
            for tool in all_tools
            if counts[tool] <= max_calls
        ]
        return sorted(underused, key=lambda x: x["calls"])

    def get_summary(self) -> str:
        """Get a usage summary report."""
        total = len(self._records)
        if total == 0:
            return "No recorded tool calls."

        success_count = sum(1 for r in self._records if r.success)
        success_rate = success_count / total * 100

        lines = [
            f"Usage Summary: {total} total call(s)",
            f"Success rate: {success_rate:.1f}%",
            "",
            "Top tools:",
        ]
        for item in self.get_hotspots(5):
            lines.append(f"  {item['tool']}: {item['calls']} calls")

        return "\n".join(lines)

    def _save(self) -> None:
        """Persist usage records to JSON."""
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "tool_name": r.tool_name,
                "success": r.success,
                "duration_ms": r.duration_ms,
                "timestamp": r.timestamp,
            }
            for r in self._records
        ]
        self._store_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        """Load usage records from JSON."""
        if not self._store_path.exists():
            return
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
            for item in data:
                self._records.append(CallRecord(**item))
        except (json.JSONDecodeError, OSError, TypeError):
            self._records = []


# ---------------------------------------------------------------------------
# AutoDeprecation
# ---------------------------------------------------------------------------


class AutoDeprecation:
    """Scan for potentially deprecated modules based on dependency and usage signals."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace = workspace_root.resolve()

    def scan(
        self,
        usage: Optional[UsageAnalytics] = None,
        failures: Optional[FailureTracker] = None,
    ) -> list[dict]:
        """Scan workspace for potentially deprecated modules.

        A module is flagged if it has:
        - Zero incoming dependency edges (no other module imports it)
        - Zero or very few tool calls in usage analytics
        """
        flags: list[dict] = []

        # Find all directories with source files
        source_exts = {".py", ".ts", ".js", ".rs", ".go", ".java"}
        modules: dict[str, dict] = {}

        for root, dirs, files in self._workspace.walk():
            # Skip ignored dirs
            ignore = {".git", "__pycache__", ".venv", "node_modules", "dist", "build"}
            dirs[:] = [d for d in dirs if d not in ignore]

            src_count = sum(1 for f in files if Path(f).suffix in source_exts)
            if src_count >= 1:
                rel = str(root.relative_to(self._workspace))
                modules[rel] = {
                    "path": root,
                    "source_count": src_count,
                    "import_count": 0,
                    "usage_count": 0,
                }

        # Count imports (heuristic: scan all source files for references to each module)
        for root, dirs, files in self._workspace.walk():
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".venv"}]
            for fname in files:
                if Path(fname).suffix not in source_exts:
                    continue
                fpath = root / fname
                try:
                    text = fpath.read_text(errors="replace").lower()
                except OSError:
                    continue
                for mod_name, mod_info in modules.items():
                    if mod_name.lower() in text and fpath.name != "__init__.py":
                        mod_info["import_count"] += 1

        # Count usage from analytics
        if usage:
            for item in usage.get_hotspots():
                for mod_name, mod_info in modules.items():
                    if item["tool"].lower() in mod_name.lower():
                        mod_info["usage_count"] += item["calls"]

        # Flag modules with zero imports AND low usage
        for mod_name, mod_info in modules.items():
            if mod_info["import_count"] == 0 and mod_info["usage_count"] <= 2:
                flags.append({
                    "module": mod_name,
                    "reason": "no_imports_and_low_usage",
                    "import_count": mod_info["import_count"],
                    "usage_count": mod_info["usage_count"],
                    "source_count": mod_info["source_count"],
                    "confidence": 0.6,
                })

        return sorted(flags, key=lambda x: x["source_count"])


# ---------------------------------------------------------------------------
# Convenience functions for MCP registration
# ---------------------------------------------------------------------------


def failure_report(workspace_root: Optional[Path] = None) -> str:
    """MCP tool: get failure report and improvement suggestions."""
    ws = (workspace_root or Path(".")).resolve()
    tracker = FailureTracker(ws)
    report = tracker.get_failure_report()
    suggestions = tracker.get_improvement_suggestions()
    if suggestions:
        report += "\n\nSuggestions:\n" + "\n".join(f"  - {s}" for s in suggestions)
    return report


def graph_analytics(workspace_root: Optional[Path] = None) -> str:
    """MCP tool: get usage analytics summary."""
    ws = (workspace_root or Path(".")).resolve()
    analytics = UsageAnalytics(ws)
    return analytics.get_summary()

"""Unit tests for Dependency Engine (FailureTracker, UsageAnalytics, AutoDeprecation)."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from my_code_agent.dep_engine import (
    AutoDeprecation,
    CallRecord,
    FailureRecord,
    FailureTracker,
    UsageAnalytics,
    failure_report,
    graph_analytics,
)


# ---------------------------------------------------------------------------
# FailureTracker
# ---------------------------------------------------------------------------


@pytest.fixture
def tracker(tmp_path: Path) -> FailureTracker:
    return FailureTracker(tmp_path)


class TestFailureTracker:
    def test_empty_report(self, tracker: FailureTracker) -> None:
        assert tracker.get_failure_report() == "No recorded failures."

    def test_record_failure(self, tracker: FailureTracker) -> None:
        tracker.record_failure(
            tool_name="read_file",
            error="File not found: /tmp/x.py",
            file_path="/tmp/x.py",
            module="src",
        )
        assert len(tracker._records) == 1
        rec = tracker._records[0]
        assert isinstance(rec, FailureRecord)
        assert rec.tool_name == "read_file"
        assert rec.error == "File not found: /tmp/x.py"
        assert rec.module == "src"

    def test_failure_report_with_records(self, tracker: FailureTracker) -> None:
        tracker.record_failure("read_file", "error 1", module="src")
        tracker.record_failure("write_file", "error 2", module="tests")
        tracker.record_failure("read_file", "error 3", module="src")

        report = tracker.get_failure_report()
        assert "3 total failure(s)" in report
        assert "read_file: 2" in report
        assert "src: 2" in report

    def test_improvement_suggestions_high_failure_tool(self, tracker: FailureTracker) -> None:
        for i in range(3):
            tracker.record_failure("read_file", f"error {i}")
        suggestions = tracker.get_improvement_suggestions()
        assert len(suggestions) >= 1
        assert "read_file" in suggestions[0]

    def test_improvement_suggestions_module_failure(self, tracker: FailureTracker) -> None:
        for i in range(2):
            tracker.record_failure("read_file", f"error {i}", module="src")
        suggestions = tracker.get_improvement_suggestions()
        assert any("src" in s for s in suggestions)

    def test_improvement_suggestions_path_errors(self, tracker: FailureTracker) -> None:
        tracker.record_failure("read_file", "path traversal detected")
        tracker.record_failure("write_file", "invalid path format")
        suggestions = tracker.get_improvement_suggestions()
        assert any("path" in s.lower() for s in suggestions)

    def test_no_path_suggestions_for_non_path_errors(self, tracker: FailureTracker) -> None:
        tracker.record_failure("read_file", "timeout")
        tracker.record_failure("write_file", "permission denied")
        suggestions = tracker.get_improvement_suggestions()
        assert not any("path" in s.lower() for s in suggestions)

    def test_get_failed_modules(self, tracker: FailureTracker) -> None:
        tracker.record_failure("r1", "e1", module="mod_a")
        tracker.record_failure("r2", "e2", module="mod_b")
        tracker.record_failure("r3", "e3", module="mod_a")
        tracker.record_failure("r4", "e4")  # no module
        failed = tracker.get_failed_modules()
        assert failed == {"mod_a", "mod_b"}

    def test_persistence_save_load(self, tracker: FailureTracker) -> None:
        tracker.record_failure("read_file", "error 1", module="src")
        tracker.record_failure("write_file", "error 2", module="tests")

        # Verify file was written
        store_path = tracker._store_path
        assert store_path.exists()
        data = json.loads(store_path.read_text(encoding="utf-8"))
        assert len(data) == 2

        # Create new tracker and load
        new_tracker = FailureTracker(tracker._workspace)
        assert len(new_tracker._records) == 2
        assert new_tracker._records[0].tool_name == "read_file"
        assert new_tracker._records[1].tool_name == "write_file"

    def test_load_corrupted_file(self, tmp_path: Path) -> None:
        store_path = tmp_path / ".agent" / "failures.json"
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text("not valid json{{", encoding="utf-8")
        tracker = FailureTracker(tmp_path)
        assert tracker._records == []

    def test_persistence_survives_empty_record(self, tracker: FailureTracker) -> None:
        # Save empty state
        tracker._save()
        # Load should still work
        new_tracker = FailureTracker(tracker._workspace)
        assert new_tracker._records == []


# ---------------------------------------------------------------------------
# UsageAnalytics
# ---------------------------------------------------------------------------


@pytest.fixture
def analytics(tmp_path: Path) -> UsageAnalytics:
    return UsageAnalytics(tmp_path)


class TestUsageAnalytics:
    def test_empty_summary(self, analytics: UsageAnalytics) -> None:
        assert analytics.get_summary() == "No recorded tool calls."

    def test_record_call(self, analytics: UsageAnalytics) -> None:
        analytics.record_call("read_file", success=True, duration_ms=50.0)
        assert len(analytics._records) == 1
        rec = analytics._records[0]
        assert isinstance(rec, CallRecord)
        assert rec.tool_name == "read_file"
        assert rec.success is True
        assert rec.duration_ms == 50.0

    def test_hotspots(self, analytics: UsageAnalytics) -> None:
        for _ in range(5):
            analytics.record_call("read_file", True, 10.0)
        for _ in range(3):
            analytics.record_call("write_file", True, 20.0)
        for _ in range(2):
            analytics.record_call("search", True, 100.0)

        hotspots = analytics.get_hotspots()
        assert len(hotspots) == 3
        assert hotspots[0]["tool"] == "read_file"
        assert hotspots[0]["calls"] == 5

    def test_hotspots_top_n(self, analytics: UsageAnalytics) -> None:
        for i in range(5):
            analytics.record_call(f"tool_{i}", True, 1.0)
        hotspots = analytics.get_hotspots(top_n=3)
        assert len(hotspots) == 3

    def test_slow_tools(self, analytics: UsageAnalytics) -> None:
        # Need min_calls=5 to qualify
        for _ in range(5):
            analytics.record_call("fast_tool", True, 1.0)
        for _ in range(5):
            analytics.record_call("slow_tool", True, 100.0)

        slow = analytics.get_slow_tools(min_calls=5)
        assert len(slow) == 2
        assert slow[0]["tool"] == "slow_tool"
        assert slow[0]["avg_duration_ms"] == 100.0

    def test_slow_tools_below_threshold(self, analytics: UsageAnalytics) -> None:
        for _ in range(3):
            analytics.record_call("some_tool", True, 500.0)
        # min_calls defaults to 5, so this shouldn't appear
        slow = analytics.get_slow_tools()
        assert all(s["tool"] != "some_tool" for s in slow)

    def test_underused_tools(self, analytics: UsageAnalytics) -> None:
        analytics.record_call("rare_tool", True, 1.0)
        analytics.record_call("rare_tool", True, 1.0)
        analytics.record_call("normal_tool", True, 1.0)
        analytics.record_call("normal_tool", True, 1.0)
        analytics.record_call("normal_tool", True, 1.0)

        underused = analytics.get_underused_tools(max_calls=2)
        assert len(underused) == 1
        assert underused[0]["tool"] == "rare_tool"
        assert underused[0]["calls"] == 2

    def test_summary_with_data(self, analytics: UsageAnalytics) -> None:
        analytics.record_call("read_file", True, 10.0)
        analytics.record_call("read_file", False, 20.0)
        analytics.record_call("write_file", True, 15.0)

        summary = analytics.get_summary()
        assert "3 total call(s)" in summary
        assert "Success rate: 66.7%" in summary
        assert "read_file" in summary

    def test_persistence_save_load(self, analytics: UsageAnalytics) -> None:
        analytics.record_call("read_file", True, 10.0)
        analytics.record_call("write_file", False, 20.0)

        store_path = analytics._store_path
        assert store_path.exists()
        data = json.loads(store_path.read_text(encoding="utf-8"))
        assert len(data) == 2

        # Reload
        new_analytics = UsageAnalytics(analytics._workspace)
        assert len(new_analytics._records) == 2

    def test_load_corrupted_file(self, tmp_path: Path) -> None:
        store_path = tmp_path / ".agent" / "usage.json"
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text("corrupt{{", encoding="utf-8")
        analytics = UsageAnalytics(tmp_path)
        assert analytics._records == []


# ---------------------------------------------------------------------------
# AutoDeprecation
# ---------------------------------------------------------------------------


class TestAutoDeprecation:
    def test_scan_empty_workspace(self, tmp_path: Path) -> None:
        ad = AutoDeprecation(tmp_path)
        flags = ad.scan()
        assert flags == []

    def test_scan_unimported_module(self, tmp_path: Path) -> None:
        pkg = tmp_path / "orphan_module"
        pkg.mkdir()
        (pkg / "utils.py").write_text("def helper(): pass\n")
        (pkg / "core.py").write_text("class Core: pass\n")

        ad = AutoDeprecation(tmp_path)
        flags = ad.scan()
        # Should be flagged (no imports + low usage)
        assert len(flags) >= 1
        orphan = [f for f in flags if f["module"] == "orphan_module"]
        assert len(orphan) == 1
        assert orphan[0]["reason"] == "no_imports_and_low_usage"

    def test_scan_imported_module_not_flagged(self, tmp_path: Path) -> None:
        shared = tmp_path / "shared"
        shared.mkdir()
        (shared / "common.py").write_text("class Common: pass\n")

        # Create a file that imports from shared
        (tmp_path / "main.py").write_text("from shared import common\n")

        ad = AutoDeprecation(tmp_path)
        flags = ad.scan()
        orphan = [f for f in flags if f["module"] == "shared"]
        assert len(orphan) == 0

    def test_scan_ignored_dirs(self, tmp_path: Path) -> None:
        # These should be skipped
        (tmp_path / ".git").mkdir(exist_ok=True)
        (tmp_path / "__pycache__").mkdir(exist_ok=True)
        (tmp_path / "node_modules").mkdir(exist_ok=True)

        (tmp_path / ".git" / "config.py").write_text("pass\n")
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "main.py").write_text("pass\n")

        ad = AutoDeprecation(tmp_path)
        flags = ad.scan()
        for flag in flags:
            assert flag["module"] != ".git"
            assert flag["module"] != "__pycache__"
            assert flag["module"] != "node_modules"

    def test_scan_with_usage_analytics(self, tmp_path: Path) -> None:
        # Clean workspace — no other source files that could create import edges
        core_pkg = tmp_path / "mycore"
        core_pkg.mkdir()
        (core_pkg / "engine.py").write_text("pass\n")

        ad = AutoDeprecation(tmp_path)
        usage = UsageAnalytics(tmp_path)
        # Tool name 'mycore_engine' contains module name 'mycore' →
        # 'mycore_engine' in 'mycore' is False — heuristic checks
        # tool IN module, so we need module name to be a suffix of tool.
        # Use module name 'engine' and tool 'mycore_engine':
        # 'mycore_engine' in 'engine' → False still.
        # The heuristic checks: item["tool"] in mod_name
        # So we need mod_name to contain tool: e.g. tool="core", mod_name="mycore"
        # But that's backwards. The heuristic is: tool_name is a substring of module_path.
        # So tool="mycore" and module="mycore" → "mycore" in "mycore" → True.
        usage.record_call("mycore", True, 5.0)
        usage.record_call("mycore", True, 5.0)
        usage.record_call("mycore", True, 5.0)

        flags = ad.scan(usage=usage)
        used = [f for f in flags if f["module"] == "mycore"]
        # usage_count should be 3 (> max_calls=2), so NOT flagged
        assert len(used) == 0, f"expected 0, got {len(used)}: {used}"

    def test_scan_multiple_languages(self, tmp_path: Path) -> None:
        # Should recognize .ts, .js, .go, .rs, .java too
        ts_dir = tmp_path / "typescript_app"
        ts_dir.mkdir()
        (ts_dir / "app.ts").write_text("export class App {}\n")

        go_dir = tmp_path / "go_service"
        go_dir.mkdir()
        (go_dir / "main.go").write_text("package main\n")

        ad = AutoDeprecation(tmp_path)
        flags = ad.scan()
        modules_flagged = {f["module"] for f in flags}
        assert "typescript_app" in modules_flagged
        assert "go_service" in modules_flagged


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


class TestConvenienceFunctions:
    def test_failure_report_empty(self, tmp_path: Path) -> None:
        result = failure_report(tmp_path)
        assert "No recorded failures." in result

    def test_failure_report_with_data(self, tmp_path: Path) -> None:
        tracker = FailureTracker(tmp_path)
        tracker.record_failure("read_file", "error 1")
        tracker.record_failure("read_file", "error 2")
        tracker.record_failure("read_file", "error 3")

        result = failure_report(tmp_path)
        assert "3 total failure(s)" in result
        assert "Suggestions:" in result
        assert "read_file" in result

    def test_graph_analytics_empty(self, tmp_path: Path) -> None:
        result = graph_analytics(tmp_path)
        assert "No recorded tool calls." in result

    def test_graph_analytics_with_data(self, tmp_path: Path) -> None:
        usage = UsageAnalytics(tmp_path)
        for _ in range(5):
            usage.record_call("read_file", True, 10.0)

        result = graph_analytics(tmp_path)
        assert "5 total call(s)" in result

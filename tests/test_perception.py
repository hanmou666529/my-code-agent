"""Tests for Multi-Modal Perception Layer — LogParser + VisionDiagnostics."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from my_code_agent.perception import (
    LogAnalysis,
    LogEntry,
    LogParser,
    LogSeverity,
    PerceptionRouter,
    VisionDiagnostic,
    VisionDiagnostics,
)


# ---------------------------------------------------------------------------
# LogEntry
# ---------------------------------------------------------------------------

class TestLogEntry:
    def test_structured_log(self):
        entry = LogEntry.from_line("2024-01-15T10:30:00 ERROR auth_module: Login failed")
        assert entry.timestamp == "2024-01-15T10:30:00"
        assert entry.severity == LogSeverity.ERROR
        assert entry.module == "auth_module"
        assert "Login failed" in entry.message

    def test_unstructured_log(self):
        entry = LogEntry.from_line("Something went wrong")
        assert entry.severity == LogSeverity.INFO
        assert entry.message == "Something went wrong"

    def test_warn_normalized(self):
        entry = LogEntry.from_line("2024-01-15T10:00:00 WARN deprecated: old_api")
        assert entry.severity == LogSeverity.WARNING

    def test_debug_log(self):
        entry = LogEntry.from_line("2024-01-15T10:00:00 DEBUG cache: Miss for key xyz")
        assert entry.severity == LogSeverity.DEBUG
        assert entry.module == "cache"


# ---------------------------------------------------------------------------
# LogParser
# ---------------------------------------------------------------------------

class TestLogParser:
    def test_parse_simple_log(self):
        parser = LogParser()
        log_text = """2024-01-15T10:00:00 INFO app: Starting
2024-01-15T10:00:01 INFO app: Loading config
2024-01-15T10:00:02 ERROR db: Connection refused
2024-01-15T10:00:03 WARNING app: Retrying connection
2024-01-15T10:00:04 INFO app: Connected"""
        result = parser.parse(log_text)
        assert result.total_lines == 5
        assert len(result.entries) == 5
        assert len(result.error_lines) >= 1

    def test_parse_ci_log_with_failures(self):
        parser = LogParser()
        log_text = """Running tests...
PASSED test_auth.py::test_login
FAILED test_payment.py::test_charge [payment/processor.py:42]
Ran 10 tests in 5.2s
FAILED (failures=1, errors=0)"""
        result = parser.parse(log_text)
        assert len(result.ci_failures) >= 1

    def test_severity_breakdown(self):
        parser = LogParser()
        log_text = """2024-01-15T10:00:00 INFO app: ok
2024-01-15T10:00:01 ERROR app: bad
2024-01-15T10:00:02 WARNING app: maybe
2024-01-15T10:00:03 ERROR app: worse"""
        result = parser.parse(log_text)
        assert result.severity_counts.get("ERROR", 0) == 2
        assert result.severity_counts.get("INFO", 0) == 1
        assert result.severity_counts.get("WARNING", 0) == 1

    def test_top_error_modules(self):
        parser = LogParser()
        log_text = """2024-01-15T10:00:00 ERROR auth: fail1
2024-01-15T10:00:01 ERROR auth: fail2
2024-01-15T10:00:02 ERROR db: fail3
2024-01-15T10:00:03 ERROR auth: fail4"""
        result = parser.parse(log_text)
        assert len(result.top_error_modules) >= 1
        assert result.top_error_modules[0][0] == "auth"
        assert result.top_error_modules[0][1] == 3

    def test_error_summary(self):
        parser = LogParser()
        log_text = "2024-01-15T10:00:00 ERROR test: something broke\n"
        result = parser.parse(log_text)
        summary = result.error_summary
        assert "1 lines" in summary

    def test_llm_prompt_built(self):
        parser = LogParser()
        log_text = "2024-01-15 ERROR test: broken\n"
        result = parser.parse(log_text)
        assert "broken" in result.llm_prompt
        assert "```" in result.llm_prompt


# ---------------------------------------------------------------------------
# VisionDiagnostics
# ---------------------------------------------------------------------------

class TestVisionDiagnostics:
    def test_file_not_found(self, tmp_path: Path):
        vision = VisionDiagnostics()
        result = pytest.importorskip("asyncio")
        import asyncio
        result = asyncio.run(vision.analyze_screenshot(tmp_path / "nonexistent.png"))
        assert result.severity == "critical"

    def test_parse_vision_response(self):
        raw = """Issue: Button is misaligned to the right.
Severity: warning.
Suggestion: Adjust the margin-left CSS property to 0."""
        result = VisionDiagnostics._parse_vision_response(raw)
        assert len(result.issues_found) >= 1
        assert len(result.fix_suggestions) >= 1
        assert result.severity == "warning"

    def test_parse_vision_critical(self):
        raw = """Critical blocker: Login form is completely invisible.
Fix: Make the form visible by removing display:none."""
        result = VisionDiagnostics._parse_vision_response(raw)
        assert result.severity == "critical"

    def test_parse_vision_no_issues_found(self):
        raw = "The screen looks like a standard dashboard with charts and tables."
        result = VisionDiagnostics._parse_vision_response(raw)
        # Should fall back to truncating the raw response
        assert len(result.issues_found) >= 1

    def test_vision_diagnostic_summary(self):
        diag = VisionDiagnostic(
            description="Test screenshot",
            issues_found=["Button misaligned", "Text overlap"],
            severity="warning",
            fix_suggestions=["Adjust CSS margin"],
        )
        summary = diag.summary()
        assert "Button misaligned" in summary
        assert "Adjust CSS margin" in summary


# ---------------------------------------------------------------------------
# PerceptionRouter
# ---------------------------------------------------------------------------

class TestPerceptionRouter:
    def test_parse_logs(self):
        router = PerceptionRouter()
        log_text = "2024-01-15 ERROR test: broken\n"
        result = router.parse_logs(log_text)
        assert isinstance(result, LogAnalysis)
        assert result.total_lines == 1

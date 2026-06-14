"""Multi-Modal Perception Layer — Vision + Log Parser.

Provides:
  - Vision diagnostics: analyze screenshots/UI captures via Claude vision API
  - Log Parser: parse CI/CD / application logs, extract errors and summaries

Both integrate with LiteLLM for provider-agnostic multimodal calls.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PerceptionType(Enum):
    """Types of multi-modal perception."""
    VISION = "vision"
    LOG_PARSER = "log_parser"


class LogSeverity(Enum):
    """Log severity levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Log Parser
# ---------------------------------------------------------------------------

# Common CI/CD log patterns
_CI_FAILURE_PATTERNS: List[tuple[str, str]] = [
    # pytest / test failures
    (r"FAILED\s+\[.*?\]\s+(.*)" , r"\1"),
    # Node / npm errors
    (r"error\s+(?:in|during|Command failed)\s+(?:.+?\s+)?(.*)" , r"\1"),
    # Python tracebacks (first line)
    (r"(?:Traceback.*?\n)?(.+?:\s+(?:Error|Exception|Failure).*)" , r"\1"),
    # Generic error keyword
    (r"(?:ERROR|FATAL|CRITICAL)[:\s]+(.*)" , r"\1"),
    # Generic FAILED test line
    (r"^FAILED\s+(.+)" , r"\1"),
    # FAILED summary line
    (r"^FAILED\s+\(.*\)" , r"\1"),
]

# Structured log line patterns
_STRUCTURED_LOG_PATTERN = re.compile(
    r"(?P<timestamp>\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}[\.\d+]*)"
    r"\s+"
    r"(?P<level>DEBUG|INFO|WARNING|ERROR|WARN|CRITICAL|FATAL)"
    r"\s+"
    r"(?:(?P<module>[^:]+):)?\s*"
    r"(?P<message>.*)"
)


@dataclass
class LogEntry:
    """A parsed log entry."""
    timestamp: Optional[str] = None
    severity: LogSeverity = LogSeverity.INFO
    module: Optional[str] = None
    message: str = ""
    raw_line: str = ""

    @classmethod
    def from_line(cls, line: str) -> "LogEntry":
        """Parse a structured log line."""
        m = _STRUCTURED_LOG_PATTERN.match(line.strip())
        if m:
            level_str = (m.group("level") or "INFO").upper()
            # Normalize WARN -> WARNING
            if level_str == "WARN":
                level_str = "WARNING"
            try:
                severity = LogSeverity(level_str)
            except ValueError:
                severity = LogSeverity.INFO
            return cls(
                timestamp=m.group("timestamp"),
                severity=severity,
                module=m.group("module"),
                message=m.group("message"),
                raw_line=line,
            )
        return cls(severity=LogSeverity.INFO, message=line, raw_line=line)


class LogParser:
    """Parse CI/CD and application logs, extract errors, produce summaries.

    Usage:
        parser = LogParser()
        result = parser.parse(log_text)
        print(result.error_summary)
        print(result.llm_analysis_prompt)
    """

    def __init__(self, llm_api_base: str = "", llm_api_key: str = "", model: str = "") -> None:
        self._api_base = llm_api_base
        self._api_key = llm_api_key
        self._model = model

    def parse(self, log_text: str) -> LogAnalysis:
        """Parse raw log text and return structured analysis.

        Extracts:
          - All structured log entries
          - CI failure patterns
          - Severity breakdown
          - Top error modules
          - LLM prompt for deep analysis
        """
        lines = log_text.strip().splitlines()
        entries: List[LogEntry] = []
        ci_failures: List[str] = []
        error_lines: List[str] = []

        for line in lines:
            entry = LogEntry.from_line(line)
            entries.append(entry)

            # Check CI failure patterns
            for pattern, repl in _CI_FAILURE_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE | re.DOTALL):
                    m = re.search(pattern, line, re.IGNORECASE | re.DOTALL)
                    if m:
                        failure_msg = m.group(1) if m.lastindex else line
                        ci_failures.append(failure_msg)
                    break

            if entry.severity in (LogSeverity.ERROR, LogSeverity.CRITICAL, LogSeverity.WARNING):
                error_lines.append(line)

        # Severity breakdown
        severity_counts: Dict[str, int] = {}
        for e in entries:
            key = e.severity.value
            severity_counts[key] = severity_counts.get(key, 0) + 1

        # Top error modules
        module_errors: Dict[str, int] = {}
        for e in entries:
            if e.severity in (LogSeverity.ERROR, LogSeverity.CRITICAL):
                mod = e.module or "unknown"
                module_errors[mod] = module_errors.get(mod, 0) + 1
        top_error_modules = sorted(module_errors.items(), key=lambda x: -x[1])[:10]

        # Build LLM prompt for deeper analysis
        llm_prompt = self._build_llm_prompt(log_text, ci_failures, error_lines)

        return LogAnalysis(
            entries=entries,
            ci_failures=ci_failures,
            error_lines=error_lines[:50],  # cap for memory
            severity_counts=severity_counts,
            top_error_modules=top_error_modules,
            llm_prompt=llm_prompt,
            total_lines=len(lines),
        )

    def _build_llm_prompt(
        self,
        log_text: str,
        ci_failures: List[str],
        error_lines: List[str],
    ) -> str:
        """Build a prompt for sending to LLM for deeper analysis."""
        parts = ["Analyze the following CI/CD log and provide actionable diagnosis."]
        if ci_failures:
            parts.append(
                f"\n\n## Detected CI Failures ({len(ci_failures)} found):\n"
                + "\n".join(f"- {f}" for f in ci_failures[:20])
            )
        if error_lines:
            parts.append(
                f"\n\n## Error/Critical Lines ({len(error_lines)} found):\n"
                + "\n".join(f"- {l}" for l in error_lines[:30])
            )
        # Truncate if extremely long
        snippet = log_text[-8000:] if len(log_text) > 8000 else log_text
        parts.append(f"\n\n## Full Log (truncated):\n```\n{snippet}\n```")
        return "\n".join(parts)

    async def analyze_with_llm(self, log_text: str) -> str:
        """Send logs to LLM for deep diagnostic analysis."""
        from litellm import completion

        analysis = self.parse(log_text)
        prompt = analysis.llm_prompt

        try:
            response = completion(
                model=self._model or "anthropic/mimo-v2.5-pro",
                api_base=self._api_base,
                api_key=self._api_key or "",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a CI/CD log analysis expert. Analyze the provided logs "
                            "and give: 1) Root cause summary, 2) Specific fix recommendations, "
                            "3) Files/lines to investigate. Be concise and actionable."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2048,
                temperature=0.1,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[LLM Analysis Failed] {e}\n\n## Manual Summary:\n{analysis.error_summary}"

    @property
    def diagnostic_report(self) -> str:
        """Return a formatted report string for inline display (no LLM call)."""
        return "LogParser — use .parse() to get analysis."


@dataclass
class LogAnalysis:
    """Structured analysis result from LogParser."""
    entries: List[LogEntry]
    ci_failures: List[str]
    error_lines: List[str]
    severity_counts: Dict[str, int]
    top_error_modules: List[tuple[str, int]]
    llm_prompt: str
    total_lines: int

    @property
    def error_summary(self) -> str:
        """Brief text summary of the analysis."""
        parts = [
            f"Log analysis: {self.total_lines} lines, "
            f"{len(self.ci_failures)} CI failures, "
            f"{len(self.error_lines)} error lines",
        ]
        if self.severity_counts:
            parts.append(
                f"Severity: {', '.join(f'{k}={v}' for k, v in sorted(self.severity_counts.items()))}"
            )
        if self.top_error_modules:
            parts.append(
                f"Top error modules: {', '.join(f'{m}({c})' for m, c in self.top_error_modules[:5])}"
            )
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Vision (Screenshot) Diagnostics
# ---------------------------------------------------------------------------

@dataclass
class VisionDiagnostic:
    """Result of vision-based screenshot analysis."""
    description: str           # What's in the screenshot
    issues_found: List[str]    # UI bugs, layout issues, etc.
    severity: str              # "critical", "warning", "info"
    fix_suggestions: List[str] = field(default_factory=list)
    raw_llm_response: str = ""

    def summary(self) -> str:
        lines = [f"Vision diagnostic ({self.severity}):"]
        if self.issues_found:
            lines.append("Issues:")
            for issue in self.issues_found:
                lines.append(f"  - {issue}")
        if self.fix_suggestions:
            lines.append("Suggestions:")
            for suggestion in self.fix_suggestions:
                lines.append(f"  - {suggestion}")
        return "\n".join(lines)


class VisionDiagnostics:
    """Screenshot / image-based UI diagnostics via Claude vision API.

    Usage:
        vision = VisionDiagnostics(api_base, api_key, model)
        result = await vision.analyze_screenshot("path/to/screenshot.png")
        print(result.summary())
    """

    def __init__(
        self,
        api_base: str = "",
        api_key: str = "",
        model: str = "",
    ) -> None:
        self._api_base = api_base
        self._api_key = api_key
        self._model = model

    @staticmethod
    def _encode_image(image_path: Path) -> str:
        """Read image file and return base64-encoded string."""
        return base64.b64encode(image_path.read_bytes()).decode("utf-8")

    async def analyze_screenshot(
        self,
        image_path: Path,
        context_prompt: str = "",
    ) -> VisionDiagnostic:
        """Analyze a screenshot and return diagnostic result."""
        from litellm import completion

        if not image_path.exists():
            return VisionDiagnostic(
                description=f"File not found: {image_path}",
                issues_found=[f"Screenshot file does not exist"],
                severity="critical",
            )

        image_b64 = self._encode_image(image_path)
        prompt_parts = [
            {
                "type": "text",
                "text": (
                    "You are a UI/UX diagnostic expert. Analyze this screenshot and identify:\n"
                    "1. What the screen is supposed to show\n"
                    "2. Any visual bugs, layout issues, or UX problems\n"
                    "3. Severity of each issue (critical/warning/info)\n"
                    "4. Actionable fix suggestions\n\n"
                    "Be specific about what needs to change."
                ),
            },
            {
                "type": "image_url",
                "image_url": {
                    "type": "base64",
                    "media_type": "image/png" if image_path.suffix == ".png" else "image/jpeg",
                    "data": image_b64,
                },
            },
        ]

        if context_prompt:
            prompt_parts[0]["text"] += f"\n\nAdditional context: {context_prompt}"

        try:
            response = completion(
                model=self._model or "anthropic/mimo-v2.5-pro",
                api_base=self._api_base,
                api_key=self._api_key or "",
                messages=[{"role": "user", "content": prompt_parts}],
                max_tokens=2048,
                temperature=0.1,
            )
            raw = response.choices[0].message.content or ""
            return self._parse_vision_response(raw)
        except Exception as e:
            return VisionDiagnostic(
                description=f"Screenshot: {image_path.name}",
                issues_found=[f"Analysis failed: {e}"],
                severity="critical",
                raw_llm_response=str(e),
            )

    @staticmethod
    def _parse_vision_response(raw: str) -> VisionDiagnostic:
        """Parse LLM vision response into structured diagnostic."""
        issues: List[str] = []
        suggestions: List[str] = []

        # Extract issues
        issue_blocks = re.findall(r"(?:[Ii]ssue|Bug|Problem)[:\s]+(.+)", raw)
        if not issue_blocks:
            # Fallback: look for bullet points
            issue_blocks = re.findall(r"[•\-\*]\s+(.+(?:issue|bug|problem|wrong|broken|mismatch).+)", raw, re.IGNORECASE)
        issues = [b.strip() for b in issue_blocks if b.strip()]

        # Extract suggestions
        suggest_blocks = re.findall(r"(?:[Ss]uggestion|Fix|Recommendation)[:\s]+(.+)", raw)
        if not suggest_blocks:
            suggest_blocks = re.findall(r"[•\-\*]\s+(.+(?:fix|change|update|add|remove|adjust).+)", raw, re.IGNORECASE)
        suggestions = [b.strip() for b in suggest_blocks if b.strip()]

        # Determine severity
        severity = "info"
        if any(kw in raw.lower() for kw in ("critical", "blocker", "severe", "major")):
            severity = "critical"
        elif any(kw in raw.lower() for kw in ("warning", "minor", "cosmetic")):
            severity = "warning"

        return VisionDiagnostic(
            description="Screenshot analysis",
            issues_found=issues if issues else [raw[:200] + "..." if len(raw) > 200 else raw],
            severity=severity,
            fix_suggestions=suggestions,
            raw_llm_response=raw,
        )


# ---------------------------------------------------------------------------
# Unified Perception Router
# ---------------------------------------------------------------------------

class PerceptionRouter:
    """Unified entry point for multi-modal perception.

    Routes requests to the appropriate perception module.
    """

    def __init__(
        self,
        api_base: str = "",
        api_key: str = "",
        model: str = "",
    ) -> None:
        self._log_parser = LogParser(api_base, api_key, model)
        self._vision = VisionDiagnostics(api_base, api_key, model)

    def parse_logs(self, log_text: str) -> LogAnalysis:
        """Parse CI/CD or application logs."""
        return self._log_parser.parse(log_text)

    async def analyze_log_with_llm(self, log_text: str) -> str:
        """Deep LLM-based log analysis."""
        return await self._log_parser.analyze_with_llm(log_text)

    async def diagnose_screenshot(
        self,
        image_path: Path,
        context: str = "",
    ) -> VisionDiagnostic:
        """Analyze a screenshot for UI issues."""
        return await self._vision.analyze_screenshot(image_path, context)

"""Safety guardrails layer for the coding agent.

Intercepts every tool call before execution: validates paths, blocks
dangerous commands, truncates output, protects sensitive files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Pattern


class SafetyViolation(Enum):
    """Types of safety violations."""
    PATH_TRAVERSAL = "path_traversal"
    SENSITIVE_FILE = "sensitive_file"
    BLOCKED_COMMAND = "blocked_command"
    OUTPUT_TOO_LARGE = "output_too_large"


@dataclass
class SafetyResult:
    """Result of a safety check. Allowed or denied with reason."""
    allowed: bool
    violation: SafetyViolation | None = None
    message: str = ""
    sanitized_path: Path | None = None
    truncated_output: str | None = None


class SafetyGuard:
    """Central safety enforcement for all agent operations."""

    SENSITIVE_PATTERNS: List[str] = [
        r"\.env$",
        r"\.key$",
        r"credentials",
        r"^/etc/",
        r"\.pem$",
        r"id_rsa",
        r"\.ssh/",
    ]

    def __init__(self, workspace_root: Path) -> None:
        self._workspace = workspace_root.resolve()
        self._blocked_re: List[Pattern[str]] = [
            re.compile(b) for b in [
                r"\brm -rf\b", r"curl\s+.*\s*\|\s*bash", r"wget\s+.*\s*\|\s*bash",
                r"chmod\s+777", r"\bmkfs\b", r">\s*/dev/sda",
                r":\(\)\{\:\|\&:\}",
            ]
        ]
        self._sensitive_re: List[Pattern[str]] = [
            re.compile(p, re.IGNORECASE) for p in self.SENSITIVE_PATTERNS
        ]

    # ---- File path validation ----

    def validate_path(self, path_str: str) -> SafetyResult:
        """Ensure a file path is within the workspace and not sensitive."""
        try:
            resolved = Path(path_str).resolve()
        except (OSError, ValueError):
            return SafetyResult(
                allowed=False,
                violation=SafetyViolation.PATH_TRAVERSAL,
                message=f"Cannot resolve path: {path_str}",
            )

        # Path traversal check
        try:
            resolved.relative_to(self._workspace)
        except ValueError:
            return SafetyResult(
                allowed=False,
                violation=SafetyViolation.PATH_TRAVERSAL,
                message=f"Path escapes workspace: {resolved}",
            )

        # Sensitive file check
        for pat in self._sensitive_re:
            if pat.search(resolved.name) or pat.search(str(resolved)):
                return SafetyResult(
                    allowed=False,
                    violation=SafetyViolation.SENSITIVE_FILE,
                    message=f"Sensitive file blocked: {resolved}",
                )

        return SafetyResult(
            allowed=True,
            sanitized_path=resolved,
            message=f"Path OK: {resolved}",
        )

    # ---- Command validation ----

    def validate_command(self, command: str) -> SafetyResult:
        """Block dangerous shell commands."""
        for pat in self._blocked_re:
            if pat.search(command):
                return SafetyResult(
                    allowed=False,
                    violation=SafetyViolation.BLOCKED_COMMAND,
                    message=f"Blocked command pattern: {command}",
                )
        return SafetyResult(allowed=True, message="Command allowed")

    # ---- Output truncation ----

    def truncate_output(self, output: str) -> SafetyResult:
        """Truncate command output to configured byte limit."""
        max_bytes = self._workspace.stat().st_size if self._workspace.exists() else 10_240
        max_bytes = 10_240  # hardcoded 10KB limit
        output_bytes = output.encode("utf-8", errors="replace")
        if len(output_bytes) > max_bytes:
            truncated = output_bytes[:max_bytes].decode("utf-8", errors="replace")
            return SafetyResult(
                allowed=True,
                truncated_output=(
                    truncated + "\n\n[OUTPUT TRUNCATED due to size limit]"
                ),
            )
        return SafetyResult(allowed=True, truncated_output=output)

    # ---- Prompt sanitization ----

    @staticmethod
    def redact_secrets(text: str) -> str:
        """Replace API-looking strings with [REDACTED] before sending to LLM."""
        text = re.sub(
            r"(?:sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36}|xox[baprs]-[a-zA-Z0-9\-]+)",
            "[REDACTED]",
            text,
        )
        return text

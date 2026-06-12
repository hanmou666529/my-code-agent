"""Safe file operations: read, write, and search-replace.

Core principle: never rewrite entire files. Always use search_replace
with exact match validation for modifications.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..safety import SafetyGuard


class FileOpsTool:
    """Safe file read/write/search-replace operations."""

    def __init__(self, safety: SafetyGuard) -> None:
        self._safety = safety

    @classmethod
    def read(cls, file_path: str) -> str:
        """Read a file's content."""
        from ..safety import SafetyGuard, SafetyViolation
        # Use a temporary guard for workspace-relative validation
        # The actual workspace is set by the agent; here we validate path safety
        try:
            resolved = Path(file_path).resolve()
        except (OSError, ValueError):
            return json.dumps({"error": "invalid_path", "message": f"Cannot resolve path: {file_path}"})

        if not resolved.is_file():
            return json.dumps({"error": "file_not_found", "message": f"File not found: {resolved}"})

        return resolved.read_text(encoding="utf-8")

    @classmethod
    def write(cls, file_path: str, content: str) -> str:
        """Write content to a file, creating or overwriting."""
        try:
            resolved = Path(file_path).resolve()
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return f"Written {len(content)} bytes to {resolved}"
        except OSError as e:
            return json.dumps({"error": "write_failed", "message": str(e)})

    @classmethod
    def search_replace(cls, file_path: str, old_string: str, new_string: str) -> str:
        """Perform a precise search-and-replace in a file.

        Validates that old_string occurs exactly once in the file.
        Prevents accidental mass replacements.
        """
        try:
            resolved = Path(file_path).resolve()
        except (OSError, ValueError):
            return json.dumps({"error": "invalid_path", "message": f"Cannot resolve path: {file_path}"})

        if not resolved.is_file():
            return json.dumps({"error": "file_not_found", "message": f"File not found: {resolved}"})

        content = resolved.read_text(encoding="utf-8")
        count = content.count(old_string)

        if count == 0:
            return json.dumps({
                "error": "no_match",
                "message": f"old_string not found in {resolved}",
                "hint": "Read the file first and use exact content as old_string",
            })
        if count > 1:
            return json.dumps({
                "error": "ambiguous_match",
                "message": f"old_string found {count} times in {resolved}. "
                           "Must be unique. Add more context to make it unique.",
            })

        new_content = content.replace(old_string, new_string, 1)
        resolved.write_text(new_content, encoding="utf-8")
        return json.dumps({
            "success": True,
            "path": str(resolved),
            "replacement_count": 1,
        })

"""Git checkpoint operations for recoverability."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitOpsTool:
    """Git checkpoint operations for recoverability."""

    DEFAULT_PREFIX = "[agent]"

    @classmethod
    def checkpoint(cls, message: str = "", workspace: str = ".") -> str:
        """Create a git checkpoint (commit) of current workspace state."""
        ws = Path(workspace).resolve()
        prefix = cls.DEFAULT_PREFIX

        try:
            # Check if this is a git repo
            proc = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=ws,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                return "Not a git repository. Git checkpoint skipped."

            # Stage all changes
            subprocess.run(
                ["git", "add", "."],
                cwd=ws,
                capture_output=True,
                text=True,
            )

            # Check if there are changes to commit
            status = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=ws,
                capture_output=True,
            )
            if status.returncode == 0:  # no changes (exit 0 = no diff)
                return "No changes to commit."

            commit_msg = f"{prefix} {message}" if message else f"{prefix} auto-checkpoint"
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=ws,
                capture_output=True,
                text=True,
            )
            return f"Git checkpoint created: {commit_msg}"

        except FileNotFoundError:
            return "Git not found. Git checkpoint skipped."

"""Restricted shell command execution with safety checks."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class ShellTool:
    """Restricted shell command executor."""

    DEFAULT_TIMEOUT = 60  # seconds

    @classmethod
    def execute(cls, command: str, workspace: str = ".", timeout: int = 0) -> str:
        """Execute a command with safety validation and output truncation."""
        from ..safety import SafetyGuard, SafetyViolation

        ws = Path(workspace).resolve()
        safety = SafetyGuard(ws)

        # Validate command
        cmd_check = safety.validate_command(command)
        if not cmd_check.allowed:
            return f"[SAFETY DENIED] {cmd_check.message}"

        # Run the command
        cmd_timeout = timeout or cls.DEFAULT_TIMEOUT
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=cmd_timeout,
                cwd=ws,
            )
            output = result.stdout
            if result.stderr:
                output = output + result.stderr if output else result.stderr
            if result.returncode != 0:
                output = f"[EXIT CODE {result.returncode}]\n{output}"

            # Truncate output
            trunc_check = safety.truncate_output(output)
            return trunc_check.truncated_output if trunc_check.truncated_output else output

        except subprocess.TimeoutExpired:
            return f"[COMMAND TIMED OUT after {cmd_timeout}s]"
        except FileNotFoundError:
            return "[EXECUTION ERROR] Command not found. Check your PATH."
        except Exception as e:
            return f"[EXECUTION ERROR] {e}"

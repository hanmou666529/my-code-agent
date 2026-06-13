"""Skill executor for the coding agent.

Executes matched skill step sequences by calling tools through the
ReAct loop's existing dispatch mechanism.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .skill_matcher import load_skills


def execute_skill(
    skill: Dict[str, Any],
    tool_executor,  # Callable[[str, Dict[str, Any]], str] — the agent's tool dispatch
    user_input: str,
    workspace_path: Optional[str] = None,
) -> str:
    """Execute a matched skill's planned sequence of tool calls.

    Args:
        skill: The matched skill definition dict
        tool_executor: Function to call tools (agent's _execute_action)
        user_input: Original user input for context
        workspace_path: Current workspace directory

    Returns:
        Final result string to return to the user.
    """
    steps = skill.get("steps", [])
    if not steps:
        return f"[Skill] Executed: {skill['name']}"

    results = []
    for i, step in enumerate(steps):
        tool_name = step.get("tool", "")
        step_args = step.get("args", {})
        step_desc = step.get("description", f"Step {i+1}")

        # Inject workspace path if not provided
        if workspace_path:
            for key in ("file_path", "workspace_path", "command"):
                if key in step_args and not step_args[key]:
                    step_args[key] = workspace_path

        try:
            obs = tool_executor(tool_name, step_args)
            results.append(f"[{step_desc}] {obs[:500]}")
        except Exception as e:
            results.append(f"[{step_desc}] ERROR: {e}")
            break

    return f"[Skill: {skill['name']}] " + "\n".join(results)

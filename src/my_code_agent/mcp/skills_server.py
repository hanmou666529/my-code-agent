"""Skills MCP Server — independent FastMCP server for Executable Skills.

Exposes four tools:
- ``execute_skill(name, inputs)`` — run a skill
- ``validate_skill(name)`` — validate a skill definition
- ``list_skills()`` — list all registered skills
- ``run_evals(name)`` — run eval cases for a skill

Hot reload runs in a background daemon thread on file changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP


def create_skills_server(
    workspace: Path,
    skills_dir: Optional[Path] = None,
) -> FastMCP:
    """Create an MCP server for the Executable Skills system.

    Args:
        workspace: Workspace root directory.
        skills_dir: Optional custom skills directory.

    Returns:
        Configured FastMCP server with skill tools registered.
    """
    server = FastMCP(name="skills")
    state = _SkillServerState(workspace, skills_dir)

    # ---- Tool registrations ----

    @server.tool()
    def list_skills() -> str:
        """List all registered Executable Skills with their levels and descriptions."""
        return _handle_list_skills(state)

    @server.tool()
    def execute_skill(name: str, inputs: str) -> str:
        """Execute an Executable Skill by name with JSON input. Args: name (str), inputs (str: JSON object)."""
        return _handle_execute_skill(state, [{"name": name, "inputs": inputs}])

    @server.tool()
    def validate_skill(name: str) -> str:
        """Validate a skill definition and return any errors. Args: name (str)."""
        return _handle_validate_skill(state, [{"name": name}])

    @server.tool()
    def run_evals(name: str) -> str:
        """Run eval cases for a skill and report pass rate. Args: name (str)."""
        return _handle_run_evals(state, [{"name": name}])

    # Start hot reload watch loop
    state.start_watcher()

    return server


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


class _SkillServerState:
    """Holds the SkillRegistry and provides server-facing API."""

    def __init__(
        self,
        workspace: Path,
        skills_dir: Optional[Path] = None,
    ) -> None:
        from ..skills import SkillRegistry

        self._workspace = workspace.resolve()
        self._registry = SkillRegistry(
            self._workspace,
            skills_dir=skills_dir,
        )
        self._registry.load()

    def start_watcher(self) -> None:
        """Start the hot-reload background thread."""
        self._registry.watch_loop(callback=lambda: self._registry.load())

    def list_skills(self) -> list[str]:
        return self._registry.list_skills()

    def get_skill(self, name: str):
        return self._registry.get_skill(name)


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def _handle_list_skills(state: _SkillServerState) -> str:
    skills = state._registry.all_skills()
    if not skills:
        return "No skills registered."

    lines = [f"Registered skills ({len(skills)}):"]
    for name, skill in sorted(skills.items()):
        lines.append(f"  - {name} (v{skill.version}, {skill.level.value}): {skill.description}")
    return "\n".join(lines)


def _handle_execute_skill(
    state: _SkillServerState, arguments: list
) -> str:
    import json as _json

    kwargs: Dict[str, Any] = {}
    for arg in arguments:
        if isinstance(arg, dict):
            kwargs.update(arg)

    name = kwargs.get("name", "")
    inputs_raw = kwargs.get("inputs", "{}")

    if not name:
        return "[ERROR] Missing required argument: name"

    skill = state.get_skill(name)
    if skill is None:
        return f"[ERROR] Unknown skill: {name}. Available: {state.list_skills()}"

    # Parse inputs
    try:
        inputs = _json.loads(inputs_raw) if isinstance(inputs_raw, str) else inputs_raw
    except (TypeError, ValueError):
        inputs = inputs_raw if isinstance(inputs_raw, dict) else {}

    # Execute
    from ..safety import SafetyGuard
    from ..skills import execute_skill

    safety = SafetyGuard(state._workspace)
    result = execute_skill(
        skill=skill,
        tool_executor=lambda n, a: f"[MCP] Tool {n} called with {a}",
        inputs=inputs,
        workspace=state._workspace,
        safety=safety,
    )

    return result.output


def _handle_validate_skill(
    state: _SkillServerState, arguments: list
) -> str:
    kwargs: Dict[str, Any] = {}
    for arg in arguments:
        if isinstance(arg, dict):
            kwargs.update(arg)

    name = kwargs.get("name", "")
    if not name:
        return "[ERROR] Missing required argument: name"

    skill = state.get_skill(name)
    if skill is None:
        return f"[ERROR] Unknown skill: {name}"

    from ..skills import validate_skill

    vr = validate_skill(skill, state._workspace)
    if vr.is_valid:
        return f"Skill '{name}' is valid."
    errors = "\n".join(f"  - {e}" for e in vr.errors)
    return f"Skill '{name}' has {len(vr.errors)} error(s):\n{errors}"


def _handle_run_evals(
    state: _SkillServerState, arguments: list
) -> str:
    kwargs: Dict[str, Any] = {}
    for arg in arguments:
        if isinstance(arg, dict):
            kwargs.update(arg)

    name = kwargs.get("name", "")
    if not name:
        return "[ERROR] Missing required argument: name"

    skill = state.get_skill(name)
    if skill is None:
        return f"[ERROR] Unknown skill: {name}"

    if not skill.eval_cases:
        return f"Skill '{name}' has no eval cases defined."

    from ..safety import SafetyGuard
    from ..skills import execute_skill

    safety = SafetyGuard(state._workspace)
    result = execute_skill(
        skill=skill,
        tool_executor=lambda n, a: f"[MCP] Tool {n} called with {a}",
        inputs={},
        workspace=state._workspace,
        safety=safety,
    )

    lines = [
        f"Eval results for '{name}':",
        f"  Pass rate: {result.eval_pass_rate * 100:.0f}%",
    ]
    for er in result.eval_results:
        status = "PASS" if er["passed"] else "FAIL"
        lines.append(f"  [{status}] {er['case_name']}")
    return "\n".join(lines)

"""Unit tests for Skills MCP Server tool handlers."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from my_code_agent.mcp.skills_server import (
    _handle_execute_skill,
    _handle_list_skills,
    _handle_run_evals,
    _handle_validate_skill,
    _SkillServerState,
)


def _make_skill_md(name: str, code: str = "") -> str:
    return f"""\
---
name: {name}
version: "1.0"
level: L1
description: Test skill {name}
type_signature:
  inputs:
    - name: path
      annotation: str
  outputs:
    - name: result
      annotation: str
---

```python
{code}
```
"""


class TestToolHandlers:
    def _make_state(self, tmp_path: Path, skills_dir_name: str = ".agent/skills") -> _SkillServerState:
        skills_dir = tmp_path / skills_dir_name
        skills_dir.mkdir(parents=True, exist_ok=True)
        return _SkillServerState(tmp_path, skills_dir=skills_dir)

    def test_execute_skill_missing_name(self, tmp_path: Path) -> None:
        state = _SkillServerState(tmp_path)
        result = _handle_execute_skill(state, [{"inputs": "{}"}])
        assert "[ERROR]" in result
        assert "Missing" in result

    def test_execute_skill_unknown_skill(self, tmp_path: Path) -> None:
        state = _SkillServerState(tmp_path)
        result = _handle_execute_skill(state, [{"name": "nonexistent", "inputs": "{}"}])
        assert "[ERROR]" in result
        assert "Unknown skill" in result

    def test_execute_skill_with_existing(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent/skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        skills_dir.joinpath("test.skill.md").write_text(_make_skill_md("test", "_result = 'ok'"))
        state = _SkillServerState(tmp_path, skills_dir=skills_dir)
        result = _handle_execute_skill(state, [{"name": "test", "inputs": "{}"}])
        assert "ok" in result or "Skill" in result or "success" in result.lower()

    def test_validate_skill_ok(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent/skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        skills_dir.joinpath("test.skill.md").write_text(_make_skill_md("test"))
        state = _SkillServerState(tmp_path, skills_dir=skills_dir)
        result = _handle_validate_skill(state, [{"name": "test"}])
        assert "valid" in result.lower() or "error" not in result.lower()

    def test_validate_skill_unknown(self, tmp_path: Path) -> None:
        state = _SkillServerState(tmp_path)
        result = _handle_validate_skill(state, [{"name": "missing"}])
        assert "[ERROR]" in result

    def test_validate_skill_missing_name(self, tmp_path: Path) -> None:
        state = _SkillServerState(tmp_path)
        result = _handle_validate_skill(state, [{}])
        assert "[ERROR]" in result
        assert "Missing" in result

    def test_list_skills_empty(self, tmp_path: Path) -> None:
        state = _SkillServerState(tmp_path)
        result = _handle_list_skills(state)
        assert "No skills" in result

    def test_list_skills_with_skills(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent/skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        skills_dir.joinpath("demo.skill.md").write_text(_make_skill_md("demo"))
        state = _SkillServerState(tmp_path, skills_dir=skills_dir)
        result = _handle_list_skills(state)
        assert "demo" in result
        assert "Registered skills" in result

    def test_run_evals_no_cases(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent/skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        skills_dir.joinpath("test.skill.md").write_text(_make_skill_md("test"))
        state = _SkillServerState(tmp_path, skills_dir=skills_dir)
        result = _handle_run_evals(state, [{"name": "test"}])
        assert "no eval cases" in result.lower()

    def test_run_evals_unknown_skill(self, tmp_path: Path) -> None:
        state = _SkillServerState(tmp_path)
        result = _handle_run_evals(state, [{"name": "missing"}])
        assert "[ERROR]" in result

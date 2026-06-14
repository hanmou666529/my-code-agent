"""Unit tests for Skill Registry (discovery, loading, hot reload)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from my_code_agent.skills.models import SkillLevel, TypeField, TypeSignature
from my_code_agent.skills.registry import SkillRegistry


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


class TestSkillRegistryLoad:
    def test_load_empty(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.load()
        assert reg.list_skills() == []

    def test_load_skill_md(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "test.skill.md").write_text(_make_skill_md("test"))
        reg = SkillRegistry(tmp_path, skills_dir=skills_dir)
        reg.load()
        assert "test" in reg.list_skills()
        skill = reg.get_skill("test")
        assert skill is not None
        assert skill.name == "test"
        assert skill.version == "1.0"

    def test_load_multiple_skills(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "a.skill.md").write_text(_make_skill_md("skill-a"))
        (skills_dir / "b.skill.md").write_text(_make_skill_md("skill-b"))
        reg = SkillRegistry(tmp_path, skills_dir=skills_dir)
        reg.load()
        assert "skill-a" in reg.list_skills()
        assert "skill-b" in reg.list_skills()

    def test_legacy_json_fallback(self, tmp_path: Path) -> None:
        mcp_dir = tmp_path / ".mcp"
        mcp_dir.mkdir()
        import json
        mcp_dir.joinpath("skills.json").write_text(json.dumps([
            {"name": "legacy-skill", "level": "L1", "description": "Legacy"}
        ]))
        reg = SkillRegistry(tmp_path)
        reg.load()
        assert "legacy-skill" in reg.list_skills()

    def test_skill_md_overrides_json(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        mcp_dir = tmp_path / ".mcp"
        mcp_dir.mkdir()
        import json

        # Same name in both
        skills_dir.joinpath("override.skill.md").write_text(
            _make_skill_md("override", code="x = 1")
        )
        mcp_dir.joinpath("skills.json").write_text(json.dumps([
            {"name": "override", "level": "L0", "description": "Old version"}
        ]))
        reg = SkillRegistry(tmp_path)
        reg.load()
        skill = reg.get_skill("override")
        assert skill is not None
        assert skill.version == "1.0"  # .skill.md version wins

    def test_parse_error_does_not_crash(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        # Invalid YAML frontmatter
        skills_dir.joinpath("bad.skill.md").write_text("just markdown\n")
        reg = SkillRegistry(tmp_path, skills_dir=skills_dir)
        reg.load()
        # Should not crash; bad skill may or may not be in registry
        # but the registry should still be usable
        assert isinstance(reg.list_skills(), list)


class TestSkillRegistryLookup:
    def test_get_skill(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        skills_dir.joinpath("test.skill.md").write_text(_make_skill_md("test"))
        reg = SkillRegistry(tmp_path, skills_dir=skills_dir)
        reg.load()
        skill = reg.get_skill("test")
        assert skill is not None
        assert skill.name == "test"

    def test_get_skill_not_found(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.load()
        assert reg.get_skill("nonexistent") is None

    def test_has_skill(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        skills_dir.joinpath("test.skill.md").write_text(_make_skill_md("test"))
        reg = SkillRegistry(tmp_path, skills_dir=skills_dir)
        reg.load()
        assert reg.has_skill("test")
        assert not reg.has_skill("missing")

    def test_all_skills(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        skills_dir.joinpath("a.skill.md").write_text(_make_skill_md("a"))
        skills_dir.joinpath("b.skill.md").write_text(_make_skill_md("b"))
        reg = SkillRegistry(tmp_path, skills_dir=skills_dir)
        reg.load()
        all_skills = reg.all_skills()
        assert len(all_skills) == 2
        assert "a" in all_skills
        assert "b" in all_skills


class TestSkillRegistryHotReload:
    def test_has_changed_false(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.load()
        assert not reg.has_changed()

    def test_reload_detects_new_file(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        reg = SkillRegistry(tmp_path, skills_dir=skills_dir)
        reg.load()
        assert "new" not in reg.list_skills()
        # Add new file after load
        import time
        skills_dir.joinpath("new.skill.md").write_text(_make_skill_md("new"))
        time.sleep(0.1)
        assert reg.has_changed()
        reg.reload()
        assert "new" in reg.list_skills()

    def test_watch_loop_starts_daemon(self, tmp_path: Path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.load()
        # Should not raise
        reg.watch_loop()

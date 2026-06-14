"""Unit tests for Executable Skill parser."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from my_code_agent.skills.parser import parse_old_skill_json, parse_skill_file
from my_code_agent.skills.models import SkillLevel


def _make_skill_md(name: str = "test-skill", code: str = "", **kwargs) -> str:
    """Helper to create a .skill.md content string."""
    fm_parts = [
        f"name: {name}",
        f'version: "{kwargs.get("version", "1.0")}"',
        f'level: {kwargs.get("level", "L1")}',
        f'description: "{kwargs.get("description", "A test skill")}"',
    ]
    ts = kwargs.get("type_signature", {"inputs": [{"name": "path", "annotation": "str"}]})
    fm_parts.append("type_signature:")
    fm_parts.append("  inputs:")
    for inp in ts.get("inputs", []):
        if isinstance(inp, dict):
            fm_parts.append(f'    - name: {inp["name"]}')
            fm_parts.append(f'      annotation: "{inp["annotation"]}"')
        else:
            fm_parts.append(f'    - "{inp}"')
    fm_parts.append("  outputs:")
    for out in ts.get("outputs", []):
        if isinstance(out, dict):
            fm_parts.append(f'    - name: {out["name"]}')
            fm_parts.append(f'      annotation: "{out["annotation"]}"')
        else:
            fm_parts.append(f'    - "{out}"')
    fm_parts.append(f"  returns_annotation: {ts.get('returns_annotation', 'str')}")

    sr = kwargs.get("structure_requirements", [])
    if sr:
        fm_parts.append("structure_requirements:")
        for s in sr:
            fm_parts.append(f"  - requires: {s.requires if hasattr(s, 'requires') else s}")
            if hasattr(s, "purpose"):
                fm_parts.append(f"    purpose: {s.purpose}")

    sc = kwargs.get("safety_constraints", [])
    if sc:
        fm_parts.append("safety_constraints:")
        for s in sc:
            fm_parts.append(f"  - {s}")

    ec = kwargs.get("eval_cases", [])
    if ec:
        fm_parts.append("eval_cases:")
        for e in ec:
            fm_parts.append(f'  - name: {e.name}')
            fm_parts.append("    inputs:")
            for k, v in e.inputs.items():
                fm_parts.append(f'      {k}: "{v}"')
            fm_parts.append("    assertions:")
            for a in e.assertions:
                fm_parts.append(f'      - "{a}"')

    mp = kwargs.get("match_patterns", [])
    if mp:
        fm_parts.append("match_patterns:")
        for m in mp:
            fm_parts.append(f"  - {m}")

    rt = kwargs.get("recommended_tools", [])
    if rt:
        fm_parts.append("recommended_tools:")
        for r in rt:
            fm_parts.append(f"  - {r}")

    return "---\n" + "\n".join(fm_parts) + "\n---\n\n```python\n" + code + "\n```\n"


class TestParseSkillFile:
    def test_basic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.skill.md"
            p.write_text(_make_skill_md())
            skill = parse_skill_file(p)
            assert skill.name == "test-skill"
            assert skill.version == "1.0"
            assert skill.level == SkillLevel.L1
            assert skill.description == "A test skill"

    def test_with_code_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.skill.md"
            p.write_text(_make_skill_md(code="print('hello')"))
            skill = parse_skill_file(p)
            assert skill.code_block == "print('hello')"
            assert skill.has_executable_code is True

    def test_no_code_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.skill.md"
            p.write_text(_make_skill_md(code=""))
            skill = parse_skill_file(p)
            assert skill.has_executable_code is False

    def test_full_definition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "full.skill.md"
            from my_code_agent.skills.models import (
                StructureRequirement, EvalCase, TypeField,
            )
            p.write_text(_make_skill_md(
                name="full",
                code="x = 1",
                version="2.0",
                level="L2",
                description="Full",
                type_signature={
                    "inputs": [
                        {"name": "path", "annotation": "str"},
                        {"name": "count", "annotation": "int"},
                    ],
                    "outputs": [{"name": "result", "annotation": "str"}],
                    "returns_annotation": "str",
                },
                structure_requirements=[
                    StructureRequirement("tests/", "check tests"),
                ],
                safety_constraints=["no-delete-public-api"],
                eval_cases=[
                    EvalCase("test1", {"path": "main.py"}, ["check"]),
                ],
                match_patterns=["refactor"],
                recommended_tools=["read_file"],
            ))
            skill = parse_skill_file(p)
            assert skill.name == "full"
            assert skill.level == SkillLevel.L2
            assert skill.version == "2.0"
            assert len(skill.type_signature.inputs) == 2
            assert skill.type_signature.inputs[1].name == "count"
            assert len(skill.structure_requirements) == 1
            assert skill.structure_requirements[0].requires == "tests/"
            assert len(skill.safety_constraints) == 1
            assert len(skill.eval_cases) == 1
            assert skill.eval_cases[0].name == "test1"
            assert skill.match_patterns == ["refactor"]
            assert skill.recommended_tools == ["read_file"]

    def test_missing_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.skill.md"
            p.write_text("just markdown\nno frontmatter\n")
            with pytest.raises(ValueError, match="No YAML frontmatter"):
                parse_skill_file(p)

    def test_invalid_level_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.skill.md"
            text = _make_skill_md()
            # Replace L1 with INVALID_LEVEL
            text = text.replace("level: L1", 'level: "INVALID_LEVEL"')
            p.write_text(text)
            skill = parse_skill_file(p)
            # Should fall back to L1
            assert skill.level == SkillLevel.L1


class TestParseOldSkillJson:
    def test_basic_conversion(self) -> None:
        entry = {
            "name": "format-code",
            "level": "L1",
            "description": "Format code",
            "match_patterns": ["format"],
            "recommended_tools": ["read_file"],
        }
        skill = parse_old_skill_json(entry)
        assert skill.name == "format-code"
        assert skill.level == SkillLevel.L1
        assert skill.code_block is None
        assert skill.has_executable_code is False
        assert skill.match_patterns == ["format"]
        assert skill.recommended_tools == ["read_file"]

    def test_with_arguments(self) -> None:
        entry = {
            "name": "gen-tests",
            "level": "L1",
            "description": "Generate tests",
            "arguments": [
                {"name": "file_path", "type": "string", "required": True},
            ],
        }
        skill = parse_old_skill_json(entry)
        assert len(skill.type_signature.inputs) == 1
        assert skill.type_signature.inputs[0].name == "file_path"

    def test_with_eval_cases(self) -> None:
        entry = {
            "name": "test-skill",
            "level": "L1",
            "description": "Test",
            "eval_cases": [
                {"name": "basic", "inputs": {"x": "1"}, "assertions": ["check"]},
            ],
        }
        skill = parse_old_skill_json(entry)
        assert len(skill.eval_cases) == 1
        assert skill.eval_cases[0].name == "basic"
        assert skill.eval_cases[0].inputs == {"x": "1"}

    def test_with_structure_requirements(self) -> None:
        entry = {
            "name": "test-skill",
            "level": "L1",
            "description": "Test",
            "structure_requirements": [
                {"requires": "tests/", "purpose": "verify"},
            ],
        }
        skill = parse_old_skill_json(entry)
        assert len(skill.structure_requirements) == 1
        assert skill.structure_requirements[0].requires == "tests/"

    def test_defaults(self) -> None:
        entry = {"name": "minimal"}
        skill = parse_old_skill_json(entry)
        assert skill.name == "minimal"
        assert skill.version == "0.1"
        assert skill.level == SkillLevel.L1
        assert skill.description == ""

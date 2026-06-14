"""Unit tests for Executable Skill validator (four-pass)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from my_code_agent.skills.models import (
    EvalCase,
    SkillDefinition,
    SkillLevel,
    StructureRequirement,
    TypeField,
    TypeSignature,
)
from my_code_agent.skills.validator import ValidationResult, validate_skill


def _make_skill(**kwargs) -> SkillDefinition:
    defaults = {
        "name": "test-skill",
        "version": "1.0",
        "level": SkillLevel.L1,
        "description": "A test skill",
        "type_signature": TypeSignature(
            inputs=[TypeField("path", "str")],
            outputs=[TypeField("result", "str")],
        ),
        "structure_requirements": [],
        "safety_constraints": [],
        "eval_cases": [],
        "code_block": None,
    }
    defaults.update(kwargs)
    return SkillDefinition(**defaults)  # type: ignore[arg-type]


class TestValidateTypeSignature:
    def test_valid_types(self, tmp_path: Path) -> None:
        skill = _make_skill(
            type_signature=TypeSignature(
                inputs=[
                    TypeField("a", "str"),
                    TypeField("b", "int"),
                    TypeField("c", "list[str]"),
                    TypeField("d", "Optional[str]"),
                ],
                outputs=[TypeField("out", "str")],
            )
        )
        vr = validate_skill(skill, tmp_path)
        assert vr.is_valid

    def test_unknown_type(self, tmp_path: Path) -> None:
        skill = _make_skill(
            type_signature=TypeSignature(
                inputs=[TypeField("x", "NotAType")],
                outputs=[],
            )
        )
        vr = validate_skill(skill, tmp_path)
        assert not vr.is_valid
        assert len(vr.errors) >= 1
        assert "NotAType" in vr.errors[0]

    def test_empty_field_name(self, tmp_path: Path) -> None:
        skill = _make_skill(
            type_signature=TypeSignature(
                inputs=[TypeField("", "str")],
                outputs=[TypeField("", "str")],
            )
        )
        vr = validate_skill(skill, tmp_path)
        assert not vr.is_valid
        assert any("empty name" in e for e in vr.errors)


class TestValidateStructureRequirements:
    def test_requirement_exists(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        skill = _make_skill(
            structure_requirements=[StructureRequirement("tests/", "verify tests")]
        )
        vr = validate_skill(skill, tmp_path)
        assert vr.is_valid

    def test_requirement_missing(self, tmp_path: Path) -> None:
        skill = _make_skill(
            structure_requirements=[StructureRequirement("missing-dir/", "should exist")]
        )
        vr = validate_skill(skill, tmp_path)
        assert not vr.is_valid
        assert any("missing required" in e for e in vr.errors)

    def test_empty_requirement_path(self, tmp_path: Path) -> None:
        skill = _make_skill(
            structure_requirements=[StructureRequirement("", "no path")]
        )
        vr = validate_skill(skill, tmp_path)
        assert not vr.is_valid
        assert any("empty" in e.lower() for e in vr.errors)


class TestValidateSafetyConstraints:
    def test_known_constraints(self, tmp_path: Path) -> None:
        skill = _make_skill(safety_constraints=["no-delete-public-api", "preserve-signature"])
        vr = validate_skill(skill, tmp_path)
        assert vr.is_valid

    def test_unknown_constraint(self, tmp_path: Path) -> None:
        skill = _make_skill(safety_constraints=["totally-made-up-constraint"])
        vr = validate_skill(skill, tmp_path)
        assert not vr.is_valid
        assert any("unrecognized" in e for e in vr.errors)


class TestValidateCodeBlock:
    def test_valid_code(self, tmp_path: Path) -> None:
        skill = _make_skill(code_block="x = 1\nprint(x)\nresult = 'ok'")
        vr = validate_skill(skill, tmp_path)
        assert vr.is_valid

    def test_empty_code(self, tmp_path: Path) -> None:
        skill = _make_skill(code_block="")
        vr = validate_skill(skill, tmp_path)
        assert vr.is_valid

    def test_none_code(self, tmp_path: Path) -> None:
        skill = _make_skill(code_block=None)
        vr = validate_skill(skill, tmp_path)
        assert vr.is_valid

    def test_syntax_error(self, tmp_path: Path) -> None:
        skill = _make_skill(code_block="def foo(\n    pass")
        vr = validate_skill(skill, tmp_path)
        assert not vr.is_valid
        assert any("syntax error" in e for e in vr.errors)

    def test_dangerous_exec(self, tmp_path: Path) -> None:
        skill = _make_skill(code_block="exec('malicious')")
        vr = validate_skill(skill, tmp_path)
        assert not vr.is_valid
        assert any("dangerous" in e for e in vr.errors)

    def test_dangerous_eval(self, tmp_path: Path) -> None:
        skill = _make_skill(code_block="result = eval(user_input)")
        vr = validate_skill(skill, tmp_path)
        assert not vr.is_valid
        assert any("dangerous" in e for e in vr.errors)

    def test_dangerous_os_system(self, tmp_path: Path) -> None:
        skill = _make_skill(code_block="import os\nos.system('rm -rf /')")
        vr = validate_skill(skill, tmp_path)
        assert not vr.is_valid
        assert any("dangerous" in e for e in vr.errors)

    def test_dangerous_socket(self, tmp_path: Path) -> None:
        skill = _make_skill(code_block="import socket\nsocket.connect(...)")
        vr = validate_skill(skill, tmp_path)
        assert not vr.is_valid
        assert any("dangerous" in e for e in vr.errors)


class TestValidateFullSkill:
    def test_all_passes(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        skill = _make_skill(
            name="good-skill",
            structure_requirements=[StructureRequirement("tests/", "verify")],
            safety_constraints=["no-delete-public-api"],
            code_block="x = 1\nresult = str(x)",
        )
        vr = validate_skill(skill, tmp_path)
        assert vr.is_valid
        assert len(vr.errors) == 0

    def test_multiple_failures(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        skill = _make_skill(
            name="bad-skill",
            type_signature=TypeSignature(
                inputs=[TypeField("x", "FakeType")],
                outputs=[TypeField("y", "str")],
            ),
            structure_requirements=[StructureRequirement("missing/", "nope")],
            safety_constraints=["unknown-constraint"],
            code_block="eval('bad')",
        )
        vr = validate_skill(skill, tmp_path)
        assert not vr.is_valid
        # Should have errors from all 4 passes
        assert len(vr.errors) >= 3  # type sig + structure + safety + code

"""Unit tests for Executable Skill data models."""

from __future__ import annotations

from pathlib import Path

import pytest

from my_code_agent.skills.models import (
    EvalCase,
    SkillDefinition,
    SkillLevel,
    SkillResult,
    StructureRequirement,
    TypeField,
    TypeSignature,
    KNOWN_SAFETY_CONSTRAINTS,
    KNOWN_TYPES,
)


class TestSkillLevel:
    def test_all_levels_exist(self) -> None:
        assert SkillLevel.L0.value == "L0"
        assert SkillLevel.L1.value == "L1"
        assert SkillLevel.L2.value == "L2"
        assert SkillLevel.L3.value == "L3"

    def test_from_string(self) -> None:
        assert SkillLevel("L0") == SkillLevel.L0
        assert SkillLevel("L3") == SkillLevel.L3


class TestTypeField:
    def test_default(self) -> None:
        tf = TypeField(name="path", annotation="str")
        assert tf.name == "path"
        assert tf.annotation == "str"

    def test_complex_annotation(self) -> None:
        tf = TypeField(name="files", annotation="list[str]")
        assert tf.annotation == "list[str]"


class TestTypeSignature:
    def test_basic(self) -> None:
        sig = TypeSignature(
            inputs=[TypeField("file_path", "str")],
            outputs=[TypeField("result", "str")],
        )
        assert len(sig.inputs) == 1
        assert len(sig.outputs) == 1
        assert sig.returns_annotation == "str"

    def test_get_input(self) -> None:
        sig = TypeSignature(
            inputs=[TypeField("a", "str"), TypeField("b", "int")],
            outputs=[],
        )
        assert sig.get_input("a").annotation == "str"
        assert sig.get_input("b").annotation == "int"
        assert sig.get_input("missing") is None

    def test_has_input(self) -> None:
        sig = TypeSignature(
            inputs=[TypeField("x", "str")],
            outputs=[],
        )
        assert sig.has_input("x")
        assert not sig.has_input("y")


class TestStructureRequirement:
    def test_basic(self) -> None:
        sr = StructureRequirement(
            requires="tests/",
            purpose="validate test compatibility",
        )
        assert sr.requires == "tests/"
        assert sr.purpose == "validate test compatibility"


class TestEvalCase:
    def test_basic(self) -> None:
        ec = EvalCase(
            name="simple test",
            inputs={"file_path": "src/main.py"},
            assertions=["contains 'success'"],
        )
        assert ec.name == "simple test"
        assert ec.inputs == {"file_path": "src/main.py"}
        assert ec.assertions == ["contains 'success'"]


class TestSkillDefinition:
    def test_minimal(self) -> None:
        sd = SkillDefinition(
            name="test-skill",
            version="1.0",
            level=SkillLevel.L0,
            description="A test skill",
            type_signature=TypeSignature(inputs=[], outputs=[]),
        )
        assert sd.name == "test-skill"
        assert sd.code_block is None
        assert sd.has_executable_code is False

    def test_with_code(self) -> None:
        sd = SkillDefinition(
            name="code-skill",
            version="1.0",
            level=SkillLevel.L1,
            description="Has code",
            type_signature=TypeSignature(inputs=[], outputs=[]),
            code_block="print('hello')",
        )
        assert sd.has_executable_code is True

    def test_empty_code_not_executable(self) -> None:
        sd = SkillDefinition(
            name="empty-skill",
            version="1.0",
            level=SkillLevel.L0,
            description="No code",
            type_signature=TypeSignature(inputs=[], outputs=[]),
            code_block="",
        )
        assert sd.has_executable_code is False

    def test_full_definition(self) -> None:
        sd = SkillDefinition(
            name="full-skill",
            version="2.0",
            level=SkillLevel.L3,
            description="Full featured",
            type_signature=TypeSignature(
                inputs=[TypeField("path", "str")],
                outputs=[TypeField("result", "str")],
            ),
            structure_requirements=[StructureRequirement("tests/", "verify")],
            safety_constraints=["no-delete-public-api"],
            eval_cases=[EvalCase("test1", {}, ["check"])],
            code_block="print('exec')",
            match_patterns=["refactor"],
            recommended_tools=["read_file"],
            context_resources=["symbol://"],
        )
        assert sd.name == "full-skill"
        assert sd.version == "2.0"
        assert sd.level == SkillLevel.L3
        assert len(sd.structure_requirements) == 1
        assert len(sd.eval_cases) == 1
        assert sd.has_executable_code is True


class TestSkillResult:
    def test_success(self) -> None:
        r = SkillResult(
            success=True,
            output="done",
            eval_pass_rate=1.0,
        )
        assert r.success is True
        assert r.eval_pass_rate == 1.0
        assert r.validation_errors == []
        assert r.eval_results == []

    def test_failed(self) -> None:
        r = SkillResult(
            success=False,
            output="error",
            eval_pass_rate=0.0,
            validation_errors=["type mismatch"],
            eval_results=[{"passed": False}],
        )
        assert r.success is False
        assert "type mismatch" in r.validation_errors


class TestConstants:
    def test_known_safety_constraints(self) -> None:
        assert "no-delete-public-api" in KNOWN_SAFETY_CONSTRAINTS
        assert "preserve-signature" in KNOWN_SAFETY_CONSTRAINTS

    def test_known_types(self) -> None:
        assert "str" in KNOWN_TYPES
        assert "int" in KNOWN_TYPES
        assert "list" in KNOWN_TYPES
        assert "Optional" in KNOWN_TYPES

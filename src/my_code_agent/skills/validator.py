"""Validator for Executable Skill definitions.

Four-pass validation:
1. Type signature — check annotations are valid Python types
2. Structure requirements — verify required paths exist in workspace
3. Safety constraints — check constraint names are recognized
4. Code block — AST syntax check + detect dangerous operations
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .models import SkillDefinition, KNOWN_SAFETY_CONSTRAINTS, KNOWN_TYPES


# Dangerous operations to detect in code blocks
DANGEROUS_PATTERNS: list[str] = [
    r"\bos\.system\s*\(",
    r"\bexec\s*\(",
    r"\beval\s*\(",
    r"\bsocket\.",
    r"\bopen\s*\(\s*[\"'][^\"']*[\"']",
]


@dataclass
class ValidationResult:
    """Result of validating a skill definition."""

    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, message: str) -> None:
        self.errors.append(message)


def validate_skill(skill: SkillDefinition, workspace: Path) -> ValidationResult:
    """Run all four validation passes on a skill definition.

    Returns a ValidationResult with any errors found.
    An empty errors list means the skill is valid.
    """
    result = ValidationResult()
    _validate_type_signature(skill, result)
    _validate_structure_requirements(skill, workspace, result)
    _validate_safety_constraints(skill, result)
    _validate_code_block(skill, result)
    return result


def _validate_type_signature(skill: SkillDefinition, result: ValidationResult) -> None:
    """Pass 1: Check type signature fields are valid Python type annotations."""
    for tf in skill.type_signature.inputs:
        if not tf.name:
            result.add_error(f"Skill '{skill.name}': input field has empty name")
            continue
        ann = tf.annotation
        # Strip optional generics: list[str] -> list, Optional[str] -> Optional
        base_type = re.split(r"\[|<", ann)[0].strip()
        if base_type not in KNOWN_TYPES:
            result.add_error(
                f"Skill '{skill.name}': unknown type '{ann}' for input '{tf.name}'. "
                f"Known types: {', '.join(sorted(KNOWN_TYPES))}"
            )

    for tf in skill.type_signature.outputs:
        if not tf.name:
            result.add_error(f"Skill '{skill.name}': output field has empty name")
            continue
        ann = tf.annotation
        base_type = re.split(r"\[|<", ann)[0].strip()
        if base_type not in KNOWN_TYPES:
            result.add_error(
                f"Skill '{skill.name}': unknown type '{ann}' for output '{tf.name}'"
            )


def _validate_structure_requirements(
    skill: SkillDefinition, workspace: Path, result: ValidationResult
) -> None:
    """Pass 2: Check workspace contains required directories/files."""
    for sr in skill.structure_requirements:
        if not sr.requires:
            result.add_error(
                f"Skill '{skill.name}': structure requirement has empty 'requires' path"
            )
            continue
        target = workspace / sr.requires
        if not target.exists():
            result.add_error(
                f"Skill '{skill.name}': missing required '{sr.requires}' "
                f"(purpose: {sr.purpose})"
            )


def _validate_safety_constraints(skill: SkillDefinition, result: ValidationResult) -> None:
    """Pass 3: Check safety constraint names are recognized."""
    for constraint in skill.safety_constraints:
        if constraint not in KNOWN_SAFETY_CONSTRAINTS:
            result.add_error(
                f"Skill '{skill.name}': unrecognized safety constraint '{constraint}'. "
                f"Known: {', '.join(sorted(KNOWN_SAFETY_CONSTRAINTS))}"
            )


def _validate_code_block(skill: SkillDefinition, result: ValidationResult) -> None:
    """Pass 4: AST syntax check + dangerous operation detection."""
    code = skill.code_block
    if code is None or not code.strip():
        return

    # Syntax check
    try:
        ast.parse(code)
    except SyntaxError as e:
        result.add_error(
            f"Skill '{skill.name}': code block has syntax error: {e}"
        )
        return  # Skip further checks if code is syntactically invalid

    # Dangerous operation detection
    source_lower = code.lower()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, source_lower):
            result.add_error(
                f"Skill '{skill.name}': code block contains dangerous operation "
                f"matching '{pattern}'"
            )

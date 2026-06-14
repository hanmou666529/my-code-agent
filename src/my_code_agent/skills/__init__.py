"""Executable Skill system package.

Provides the core infrastructure for Executable Skills — type-safe skill
definitions with YAML frontmatter parsing, four-pass validation, sandboxed
execution, and a hot-reloadable registry.
"""

from __future__ import annotations

from .models import (
    EvalCase,
    SkillDefinition,
    SkillLevel,
    SkillResult,
    StructureRequirement,
    TypeField,
    TypeSignature,
)
from .parser import parse_old_skill_json, parse_skill_file
from .registry import SkillRegistry
from .validator import ValidationResult, validate_skill
from .executor import execute_skill

__all__ = [
    # Models
    "EvalCase",
    "SkillDefinition",
    "SkillLevel",
    "SkillResult",
    "StructureRequirement",
    "TypeField",
    "TypeSignature",
    # Parser
    "parse_skill_file",
    "parse_old_skill_json",
    # Validator
    "ValidationResult",
    "validate_skill",
    # Executor
    "execute_skill",
    # Registry
    "SkillRegistry",
]

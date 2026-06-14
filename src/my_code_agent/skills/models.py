"""Executable Skill data models.

Defines the complete type-safe data structures for the Executable Skill
system: type signatures, structure requirements, eval cases, and the
superset SkillDefinition that subsumes the old skills.json format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class SkillLevel(Enum):
    """Skill complexity levels. L0 = single tool, L3 = multi-step pipeline."""

    L0 = "L0"  # Single tool call, no planning
    L1 = "L1"  # Simple tool sequence
    L2 = "L2"  # Multi-step with conditional logic
    L3 = "L3"  # Full pipeline with eval gate


@dataclass
class TypeField:
    """A single field in a type signature."""

    name: str
    annotation: str  # Python type annotation as string, e.g. "str", "list[str]"


@dataclass
class TypeSignature:
    """Declared input/output contract for a skill."""

    inputs: list[TypeField]
    outputs: list[TypeField]
    returns_annotation: str = "str"

    def get_input(self, name: str) -> Optional[TypeField]:
        for f in self.inputs:
            if f.name == name:
                return f
        return None

    def has_input(self, name: str) -> bool:
        return any(f.name == name for f in self.inputs)


@dataclass
class StructureRequirement:
    """A required directory or file in the workspace."""

    requires: str  # path pattern (directory or file)
    purpose: str   # why this is required


@dataclass
class EvalCase:
    """A test case bundled with a skill."""

    name: str
    inputs: dict[str, str]  # input values as strings
    assertions: list[str]   # natural-language assertions to check


@dataclass
class SkillDefinition:
    """Complete skill definition — superset of old skills.json entries."""

    name: str
    version: str
    level: SkillLevel
    description: str
    type_signature: TypeSignature
    structure_requirements: list[StructureRequirement] = field(default_factory=list)
    safety_constraints: list[str] = field(default_factory=list)
    eval_cases: list[EvalCase] = field(default_factory=list)
    code_block: Optional[str] = None  # Python code to execute (None for legacy)
    match_patterns: list[str] = field(default_factory=list)
    recommended_tools: list[str] = field(default_factory=list)
    context_resources: list[str] = field(default_factory=list)

    @property
    def has_executable_code(self) -> bool:
        return self.code_block is not None and len(self.code_block.strip()) > 0


@dataclass
class SkillResult:
    """Structured result of skill execution."""

    success: bool
    output: str
    eval_pass_rate: float  # 0.0 to 1.0
    eval_results: list[dict] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    execution_time_ms: float = 0.0


# Built-in safety constraint names recognized by the validator
KNOWN_SAFETY_CONSTRAINTS: set[str] = {
    "no-delete-public-api",
    "preserve-signature",
    "no-format-changes",
    "no-style-only-changes",
    "preserve-existing-tests",
    "no-dangerous-ops",
}

# Built-in type names recognized by the type validator
KNOWN_TYPES: set[str] = {
    "str", "int", "float", "bool", "bytes", "None",
    "list", "dict", "set", "tuple",
    "Optional", "Union", "Any",
}

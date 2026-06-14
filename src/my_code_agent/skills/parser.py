"""Parser for Executable Skill definition files.

Supports two formats:
1. ``.skill.md`` files with YAML frontmatter + Python code block
2. Legacy ``skills.json`` entries (backward compatible)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .models import (
    EvalCase,
    SkillDefinition,
    SkillLevel,
    StructureRequirement,
    TypeField,
    TypeSignature,
)


def parse_skill_file(path: Path) -> SkillDefinition:
    """Parse a ``.skill.md`` file: YAML frontmatter + Python code block.

    Expected format:
    ```markdown
    ---
    name: refactor-function
    version: "1.0"
    ...
    ---

    ```python
    # executable code here
    ```
    """
    text = path.read_text(encoding="utf-8")

    # Extract YAML frontmatter (between --- delimiters)
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*", text, re.DOTALL)
    if not fm_match:
        raise ValueError(f"No YAML frontmatter found in {path}")

    fm_text = fm_match.group(1)
    raw: Dict[str, Any] = yaml.safe_load(fm_text)
    if not isinstance(raw, dict):
        raise ValueError(f"Frontmatter in {path} is not a YAML mapping")

    # Extract first Python code block
    code_match = re.search(r"```(?:python|py)?\n(.*?)```", text, re.DOTALL)
    code_block = code_match.group(1).strip() if code_match else None

    return _build_definition(raw, code_block)


def parse_old_skill_json(entry: Dict[str, Any]) -> SkillDefinition:
    """Convert a legacy ``skills.json`` entry to SkillDefinition.

    Old format has no type_signature, structure_requirements, or code_block.
    This enables backward compatibility — old skills still work as metadata.
    """
    level_str = entry.get("level", "L1")
    try:
        level = SkillLevel(level_str)
    except ValueError:
        level = SkillLevel.L1

    # Build minimal type signature from recommended_tools if available
    inputs: list[TypeField] = []
    if "arguments" in entry:
        for arg in entry["arguments"]:
            inputs.append(TypeField(
                name=arg["name"],
                annotation=arg.get("type", "str"),
            ))
    elif entry.get("steps"):
        inputs.append(TypeField(name="skill_name", annotation="str"))

    outputs: list[TypeField] = [TypeField(name="result", annotation="str")]

    # Parse eval cases if present
    eval_cases: list[EvalCase] = []
    for ec in entry.get("eval_cases", []):
        if isinstance(ec, dict):
            eval_cases.append(EvalCase(
                name=ec.get("name", "unnamed"),
                inputs=ec.get("inputs", {}),
                assertions=ec.get("assertions", []),
            ))

    # Parse structure requirements
    structure_reqs: list[StructureRequirement] = []
    for sr in entry.get("structure_requirements", []):
        if isinstance(sr, dict):
            structure_reqs.append(StructureRequirement(
                requires=sr.get("requires", ""),
                purpose=sr.get("purpose", ""),
            ))
        elif isinstance(sr, str):
            structure_reqs.append(StructureRequirement(
                requires=sr, purpose="",
            ))

    return SkillDefinition(
        name=entry["name"],
        version=entry.get("version", "0.1"),
        level=level,
        description=entry.get("description", ""),
        type_signature=TypeSignature(inputs=inputs, outputs=outputs),
        structure_requirements=structure_reqs,
        safety_constraints=entry.get("safety_constraints", []),
        eval_cases=eval_cases,
        code_block=None,  # Legacy skills have no executable code
        match_patterns=entry.get("match_patterns", []),
        recommended_tools=entry.get("recommended_tools", []),
        context_resources=entry.get("context_resources", []),
    )


def _build_definition(raw: Dict[str, Any], code_block: Optional[str]) -> SkillDefinition:
    """Build a SkillDefinition from parsed YAML data."""
    # Level
    level_str = raw.get("level", "L1")
    try:
        level = SkillLevel(level_str)
    except ValueError:
        level = SkillLevel.L1

    # Type signature
    inputs: list[TypeField] = []
    outputs: list[TypeField] = []
    returns_annotation = "str"

    ts = raw.get("type_signature", {})
    if isinstance(ts, dict):
        for tf in ts.get("inputs", []) or []:
            if isinstance(tf, dict):
                inputs.append(TypeField(name=tf["name"], annotation=tf.get("annotation", "str")))
            elif isinstance(tf, str):
                name, _, ann = tf.partition(":")
                inputs.append(TypeField(name=name.strip(), annotation=ann.strip() or "str"))
        for tf in ts.get("outputs", []) or []:
            if isinstance(tf, dict):
                outputs.append(TypeField(name=tf["name"], annotation=tf.get("annotation", "str")))
            elif isinstance(tf, str):
                name, _, ann = tf.partition(":")
                outputs.append(TypeField(name=name.strip(), annotation=ann.strip() or "str"))
        returns_annotation = ts.get("returns_annotation", "str")

    # Structure requirements
    structure_reqs: list[StructureRequirement] = []
    for sr in (raw.get("structure_requirements") or []):
        if isinstance(sr, dict):
            structure_reqs.append(StructureRequirement(
                requires=sr.get("requires", ""),
                purpose=sr.get("purpose", ""),
            ))
        elif isinstance(sr, str):
            structure_reqs.append(StructureRequirement(requires=sr, purpose=""))

    # Eval cases
    eval_cases: list[EvalCase] = []
    for ec in (raw.get("eval_cases") or []):
        if isinstance(ec, dict):
            eval_cases.append(EvalCase(
                name=ec.get("name", "unnamed"),
                inputs=ec.get("inputs", {}),
                assertions=ec.get("assertions", []),
            ))

    return SkillDefinition(
        name=raw["name"],
        version=str(raw.get("version", "0.1")),
        level=level,
        description=raw.get("description", ""),
        type_signature=TypeSignature(
            inputs=inputs,
            outputs=outputs,
            returns_annotation=returns_annotation,
        ),
        structure_requirements=structure_reqs,
        safety_constraints=raw.get("safety_constraints", []),
        eval_cases=eval_cases,
        code_block=code_block,
        match_patterns=raw.get("match_patterns", []),
        recommended_tools=raw.get("recommended_tools", []),
        context_resources=raw.get("context_resources", []),
    )

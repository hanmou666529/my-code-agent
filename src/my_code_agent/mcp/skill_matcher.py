"""Skill intent matching for the coding agent.

Matches user input against predefined skill definitions using keyword
matching with confidence scoring. Falls back to LLM decision if
confidence is below threshold.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..tools import list_tools

# Default skills file location
DEFAULT_SKILLS_PATH = Path(".mcp/skills.json")


def load_skills(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load skill definitions from a JSON file."""
    skills_file = path or DEFAULT_SKILLS_PATH
    if not skills_file.exists():
        return []

    try:
        with skills_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def match_skill(
    user_input: str,
    skills: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Match user input against skill definitions.

    Returns the highest-confidence matching skill, or None if no
    confidence match is found.

    Matching strategy:
    1. Exact tool name match (L0)
    2. Keyword pattern match with confidence scoring (L1)
    3. None (let LLM decide with raw tools)
    """
    if skills is None:
        skills = load_skills()

    if not skills:
        return None

    input_lower = user_input.lower()
    best_match: Optional[Dict[str, Any]] = None
    best_score = 0

    for skill in skills:
        score = _score_match(input_lower, skill)
        if score > best_score:
            best_score = score
            best_match = skill

    # Confidence threshold: at least one keyword must match
    # Simple skills (level L0/L1) need score >= 1
    # Task skills (level L2/L3) need score >= 2
    if best_match is None:
        return None

    level = best_match.get("level", "L1")
    threshold = 1 if level in ("L0", "L1") else 2

    if best_score >= threshold:
        return best_match

    return None


def _score_match(
    input_lower: str,
    skill: Dict[str, Any],
) -> int:
    """Score how well the user input matches a skill.

    Returns a confidence score. Higher = better match.
    """
    score = 0
    match_patterns = skill.get("match_patterns", [])
    skill_name = skill.get("name", "").lower()

    # Check each match pattern
    for pattern in match_patterns:
        pattern_lower = pattern.lower()
        if pattern_lower in input_lower:
            # Exact substring match
            score += 1
            # Bonus for matching the skill name itself
            if skill_name in input_lower:
                score += 2

    return score

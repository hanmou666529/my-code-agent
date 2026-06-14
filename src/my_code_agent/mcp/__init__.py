"""MCP (Model Context Protocol) integration package.

Wraps existing agent tools as MCP server tools, provides a client bridge
for the ReAct loop, implements the Skills system (legacy JSON + Executable
Skills), and provides a standalone Skills MCP server.
"""

from .wrappers import create_codebase_server
from .bridge import MCPBridge
from .skill_matcher import match_skill
from .skill_executor import execute_skill
from .skills_server import create_skills_server

# Re-export Executable Skills system from the new skills package
from ..skills import (
    SkillDefinition,
    SkillLevel,
    SkillRegistry,
    SkillResult,
    parse_skill_file,
    parse_old_skill_json,
    validate_skill,
)

__all__ = [
    # MCP server
    "create_codebase_server",
    # Bridge
    "MCPBridge",
    # Skill matching & execution (legacy)
    "match_skill",
    "execute_skill",
    # Skills MCP server
    "create_skills_server",
    # Executable Skills system
    "SkillDefinition",
    "SkillLevel",
    "SkillRegistry",
    "SkillResult",
    "parse_skill_file",
    "parse_old_skill_json",
    "validate_skill",
]

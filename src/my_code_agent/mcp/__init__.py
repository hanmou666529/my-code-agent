"""MCP (Model Context Protocol) integration package.

Wraps existing agent tools as MCP server tools, provides a client bridge
for the ReAct loop, and implements the Skills system.
"""

from .wrappers import create_codebase_server
from .bridge import MCPBridge
from .skill_matcher import match_skill
from .skill_executor import execute_skill

__all__ = [
    "create_codebase_server",
    "MCPBridge",
    "match_skill",
    "execute_skill",
]

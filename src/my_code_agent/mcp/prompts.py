"""MCP prompt definitions for the coding agent.

These are MCP Prompt templates that can be used for L3/L2 Skills.
Prompts provide structured templates for common workflows.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# MCP Prompt templates — structured definitions for Skills
PROMPT_TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "refactor-function",
        "description": "Safely refactor a specified function while preserving tests",
        "arguments": [
            {"name": "file_path", "type": "string", "required": True},
            {"name": "function_name", "type": "string", "required": True},
            {"name": "goal", "type": "string", "required": True},
        ],
        "recommended_tools": ["read_file", "search_replace", "git_checkpoint"],
        "context_resources": ["symbol://"],
        "safety_constraints": ["no-delete-public-api", "preserve-signature"],
    },
    {
        "name": "format-code",
        "description": "Format Python code using ruff or black",
        "arguments": [
            {"name": "file_path", "type": "string", "required": True},
        ],
        "recommended_tools": ["read_file", "search_replace"],
        "context_resources": [],
        "safety_constraints": ["no-format-changes"],
    },
    {
        "name": "lint-fix",
        "description": "Fix lint errors in the given file",
        "arguments": [
            {"name": "file_path", "type": "string", "required": True},
        ],
        "recommended_tools": ["read_file", "search_replace"],
        "context_resources": [],
        "safety_constraints": ["no-style-only-changes"],
    },
    {
        "name": "gen-tests",
        "description": "Generate unit tests for a given function or class",
        "arguments": [
            {"name": "file_path", "type": "string", "required": True},
            {"name": "target", "type": "string", "required": True},
            {"name": "test_dir", "type": "string", "required": False},
        ],
        "recommended_tools": ["read_file", "write_file"],
        "context_resources": ["symbol://"],
        "safety_constraints": ["preserve-existing-tests"],
    },
    {
        "name": "search-refactor",
        "description": "Find all usages of a symbol and refactor them consistently",
        "arguments": [
            {"name": "symbol_name", "type": "string", "required": True},
            {"name": "new_name", "type": "string", "required": True},
        ],
        "recommended_tools": ["search_symbols", "read_file", "search_replace"],
        "context_resources": ["symbol://"],
        "safety_constraints": ["no-delete-public-api"],
    },
]


def get_prompt_template(name: str) -> Optional[Dict[str, Any]]:
    """Get a prompt template by name."""
    for template in PROMPT_TEMPLATES:
        if template["name"] == name:
            return template
    return None


def list_prompt_templates() -> List[str]:
    """Return the list of available template names."""
    return [t["name"] for t in PROMPT_TEMPLATES]

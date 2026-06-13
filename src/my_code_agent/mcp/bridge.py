"""MCP client bridge for the ReAct loop.

Connects the agent's sync ReAct loop to the MCP server.
For in-process mode, directly dispatches tool calls to the
existing TOOL_REGISTRY.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


class MCPBridge:
    """In-process MCP bridge for the ReAct loop.

    In production this would connect to an external MCP server via stdio.
    For now, it wraps the existing TOOL_REGISTRY with workspace context.
    """

    def __init__(self, workspace_path: Optional[Path] = None) -> None:
        self._workspace = workspace_path or Path(".")

    def call_tool(
        self, name: str, arguments: Dict[str, Any]
    ) -> str:
        """Synchronously call an MCP tool by name.

        Args:
            name: Tool name (e.g., "read_file", "write_file")
            arguments: Tool arguments dict

        Returns:
            Tool result as a string (mimics the observation format).
        """
        from ..tools import get_tool, list_tools

        if name not in list_tools():
            return f"[MCP ERROR] Unknown tool: {name}"

        tool_fn = get_tool(name)
        if tool_fn is None:
            return f"[MCP ERROR] Tool not found: {name}"

        try:
            return tool_fn(**arguments)
        except Exception as e:
            return f"[MCP ERROR] {name} failed: {e}"

    def list_tools(self) -> list[str]:
        """Return the list of available MCP tool names."""
        from ..tools import list_tools
        return list_tools()

    async def close(self) -> None:
        """Clean up the MCP client connection."""
        pass

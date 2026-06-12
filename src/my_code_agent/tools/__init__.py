"""Tools package for the coding agent.

Exposes a tool registry mapping action names to callables.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from .file_ops import FileOpsTool
from .git_ops import GitOpsTool
from .search import SearchTool
from .shell import ShellTool

# Instrumentation
_total_calls: int = 0
_total_errors: int = 0


def instrument_calls():
    """Return (total_calls, total_errors) counters for monitoring."""
    return _total_calls, _total_errors


def increment_calls(n: int = 1):
    """Increment the call counter by n."""
    global _total_calls
    _total_calls += n


def increment_errors(n: int = 1):
    """Increment the error counter by n."""
    global _total_errors
    _total_errors += n


# Tool definitions
tools: Dict[str, Callable[..., str]] = {
    "read_file": FileOpsTool.read,
    "write_file": FileOpsTool.write,
    "search_replace": FileOpsTool.search_replace,
    "search_symbols": SearchTool.search_symbols,
    "rg_search": SearchTool.rg_search,
    "execute_command": ShellTool.execute,
    "git_checkpoint": GitOpsTool.checkpoint,
}


def get_tool(name: str) -> Callable[..., str] | None:
    """Return the tool function by name, or None if not found."""
    return tools.get(name)


def list_tools() -> list[str]:
    """Return the list of available tool names."""
    return list(tools.keys())

"""MCP Server wrappers for existing agent tools.

Wraps the existing tool functions (file_ops, search, shell, git_ops)
as MCP server tools using FastMCP. Preserves original function signatures
and error formats to ensure backward compatibility.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from mcp.server.fastmcp import FastMCP

from ..safety import SafetyGuard, SafetyViolation
from ..tools import file_ops, search, shell, git_ops
from ..tools import list_tools as list_tools_func


# ---- Tool wrapper factory ----

def _wrap_read_file(fn: Callable[..., str], safety: SafetyGuard) -> Callable[..., str]:
    """Wrap read_file with workspace validation."""
    def wrapped(file_path: str, **kwargs: Any) -> str:
        result = safety.validate_path(file_path)
        if not result.allowed:
            return f"[SAFETY DENIED] {result.message}"
        try:
            return result.sanitized_path.read_text(encoding="utf-8")
        except OSError as e:
            return f"[ERROR] Cannot read file: {e}"
    return wrapped


def _wrap_write_file(fn: Callable[..., str], safety: SafetyGuard) -> Callable[..., str]:
    """Wrap write_file with workspace validation."""
    def wrapped(file_path: str, content: str, **kwargs: Any) -> str:
        result = safety.validate_path(file_path)
        if not result.allowed:
            return f"[SAFETY DENIED] {result.message}"
        try:
            result.sanitized_path.write_text(content, encoding="utf-8")
            return f"Written {len(content)} bytes to {result.sanitized_path}"
        except OSError as e:
            return f"[ERROR] Cannot write file: {e}"
    return wrapped


def _wrap_search_replace(fn: Callable[..., str], safety: SafetyGuard) -> Callable[..., str]:
    """Wrap search_replace with workspace validation."""
    def wrapped(file_path: str, old_string: str, new_string: str, **kwargs: Any) -> str:
        result = safety.validate_path(file_path)
        if not result.allowed:
            return f"[SAFETY DENIED] {result.message}"
        try:
            content = result.sanitized_path.read_text(encoding="utf-8")
            count = content.count(old_string)
            if count == 0:
                return f'{{"error": "no_match", "message": "old_string not found"}}'
            if count > 1:
                return f'{{"error": "ambiguous_match", "message": "found {count} times"}}'
            new_content = content.replace(old_string, new_string, 1)
            result.sanitized_path.write_text(new_content, encoding="utf-8")
            return '{"success": true, "replacement_count": 1}'
        except OSError as e:
            return f"[ERROR] search_replace failed: {e}"
    return wrapped


def _wrap_search_symbols(fn: Callable[..., str], context_engine: Any) -> Callable[..., str]:
    """Wrap search_symbols with context engine."""
    def wrapped(query: str, **kwargs: Any) -> str:
        matches = context_engine.search_symbols(query)
        if not matches:
            return "No matching symbols found."
        lines = []
        for s in matches:
            lines.append(f"  {s.file}:{s.line}  {s.kind}  {s.name}")
            if s.signature:
                lines.append(f"    signature: {s.signature}")
            if s.docstring:
                lines.append(f"    doc: {s.docstring[:120]}")
        return "\n".join(lines)
    return wrapped


def _wrap_rgrep_search(fn: Callable[..., str], workspace: Path) -> Callable[..., str]:
    """Wrap rg_search with workspace context."""
    def wrapped(pattern: str, workspace_path: Optional[str] = None, **kwargs: Any) -> str:
        target = Path(workspace_path) if workspace_path else workspace
        results = context_module.ContextEngine.rg_search(pattern, target, max_results=50)
        if not results:
            return "No matches found."
        return "\n".join(results[:50])

    import sys
    # Import the module, not the class directly to avoid circular issues
    ctx_mod = sys.modules.get(__name__.rsplit(".", 1)[0] + ".context")
    if ctx_mod is None:
        from .. import context as context_module
        ctx_mod = context_module

    def wrapped_with_import(pattern: str, workspace_path: Optional[str] = None, **kwargs: Any) -> str:
        target = Path(workspace_path) if workspace_path else workspace
        results = context_module.ContextEngine.rg_search(pattern, target, max_results=50)
        if not results:
            return "No matches found."
        return "\n".join(results[:50])

    return wrapped_with_import


def _wrap_execute_command(fn: Callable[..., str], safety: SafetyGuard, workspace: Path) -> Callable[..., str]:
    """Wrap execute_command with safety validation."""
    def wrapped(command: str, workspace_path: Optional[str] = None, timeout: int = 0, **kwargs: Any) -> str:
        target = Path(workspace_path) if workspace_path else workspace
        cmd_check = safety.validate_command(command)
        if not cmd_check.allowed:
            return f"[SAFETY DENIED] {cmd_check.message}"
        return shell.ShellTool.execute(command, str(target), timeout)
    return wrapped


def _wrap_git_checkpoint(fn: Callable[..., str], workspace: Path) -> Callable[..., str]:
    """Wrap git_checkpoint with workspace context."""
    def wrapped(message: str = "", workspace_path: Optional[str] = None, **kwargs: Any) -> str:
        target = Path(workspace_path) if workspace_path else workspace
        return git_ops.GitOpsTool.checkpoint(message, str(target))
    return wrapped


# ---- Server factory ----

def create_codebase_server(workspace_path: Path) -> FastMCP:
    """Create an MCP server that wraps all existing agent tools.

    Each tool is wrapped to inject workspace context and safety checks
    while preserving the original function signature and error format.
    """
    server = FastMCP(name="codebase", version="1.0.0")
    safety = SafetyGuard(workspace_path)

    # Import context engine lazily to avoid circular imports
    from ..context import ContextEngine

    # Define all tool handlers
    tool_handlers = {
        "read_file": _wrap_read_file(file_ops.FileOpsTool.read, safety),
        "write_file": _wrap_write_file(file_ops.FileOpsTool.write, safety),
        "search_replace": _wrap_search_replace(file_ops.FileOpsTool.search_replace, safety),
        "search_symbols": _wrap_search_symbols(search.SearchTool.search_symbols, ContextEngine(workspace_path)),
        "rg_search": _wrap_rgrep_search(search.SearchTool.rg_search, workspace_path),
        "execute_command": _wrap_execute_command(shell.ShellTool.execute, safety, workspace_path),
        "git_checkpoint": _wrap_git_checkpoint(git_ops.GitOpsTool.checkpoint, workspace_path),
    }

    # MCP tool descriptions (human-readable)
    tool_descriptions: Dict[str, str] = {
        "read_file": "Read the complete content of a file. Args: file_path (str)",
        "write_file": "Write content to a file. Args: file_path (str), content (str)",
        "search_replace": "Search and replace in a file. Args: file_path (str), old_string (str), new_string (str)",
        "search_symbols": "Search code symbols. Args: query (str)",
        "rg_search": "Search file contents using ripgrep. Args: pattern (str), workspace_path (str)",
        "execute_command": "Execute a shell command with safety validation. Args: command (str), workspace_path (str), timeout (int)",
        "git_checkpoint": "Create a git commit checkpoint. Args: message (str), workspace_path (str)",
    }

    # Register all tools with FastMCP
    for tool_name, handler in tool_handlers.items():
        description = tool_descriptions.get(tool_name, "")
        server.add_tool(handler, name=tool_name, description=description)

    # Register resources
    @server.list_resources()
    async def list_resources():
        return []  # Dynamic resources handled below

    return server

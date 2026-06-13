"""MCP resource definitions for the coding agent.

Exposes the ContextEngine's functionality as MCP Resources, enabling
dynamic context loading instead of static system prompt injection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..context import ContextEngine


class ResourceRegistry:
    """Registry of MCP Resource handlers for the codebase."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace = workspace_root.resolve()
        self._engine = ContextEngine(workspace_root)

    def get_resource(self, uri: str) -> str:
        """Get a resource by URI.

        Supported URI schemes:
        - `symbol://workspace/{file}?query={name}` — search for symbols
        - `context://file/{path}?lines={n}` — get file context with line numbers
        """
        if uri.startswith("symbol://"):
            return self._handle_symbol_resource(uri)
        elif uri.startswith("context://"):
            return self._handle_context_resource(uri)
        else:
            return f"Unknown resource scheme: {uri}"

    def _handle_symbol_resource(self, uri: str) -> str:
        """Handle symbol:// URIs.

        Examples:
        - symbol://workspace/src/main.py?query=greet
        - symbol://workspace/src/main.py
        """
        # Parse URI: symbol://workspace/{path}?query={q}
        path_part = uri[len("symbol://"):].split("?")[0]
        query = ""
        if "?" in uri:
            query = uri.split("query=")[1].split("&")[0] if "query=" in uri else ""

        file_path = Path(path_part)
        if not file_path.is_absolute():
            file_path = self._workspace / file_path

        # Index the file if needed
        self._engine.index_file(file_path)

        if query:
            matches = self._engine.search_symbols(query)
            if not matches:
                return "No matching symbols found."
            lines = []
            for s in matches:
                lines.append(f"  {s.file}:{s.line}  {s.kind}  {s.name}")
                if s.signature:
                    lines.append(f"    signature: {s.signature}")
            return "\n".join(lines)
        else:
            # Return all symbols from the file
            return f"Symbols indexed from {file_path}"

    def _handle_context_resource(self, uri: str) -> str:
        """Handle context:// URIs.

        Examples:
        - context://file/src/main.py?lines=20
        """
        # Parse URI: context://file/{path}?lines={n}
        path_part = uri[len("context://file/"):].split("?")[0]
        lines = 20
        if "?lines=" in uri:
            try:
                lines = int(uri.split("lines=")[1].split("&")[0])
            except ValueError:
                pass

        file_path = Path(path_part)
        if not file_path.is_absolute():
            file_path = self._workspace / file_path

        return self._engine.get_file_context(file_path, surrounding_lines=lines)

    def list_resources(self) -> list[str]:
        """Return the list of available resource URIs."""
        return []  # Dynamic discovery

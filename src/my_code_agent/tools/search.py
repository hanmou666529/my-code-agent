"""Code search tool backed by ContextEngine and ripgrep."""

from __future__ import annotations

from pathlib import Path

from ..context import ContextEngine


class SearchTool:
    """Code search tool backed by ContextEngine and ripgrep."""

    def __init__(self, context_engine: ContextEngine) -> None:
        self._engine = context_engine

    def search_symbols(self, query: str) -> str:
        """Search the symbol index. Returns formatted results."""
        matches = self._engine.search_symbols(query)
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

    @staticmethod
    def rg_search(pattern: str, workspace: str = ".") -> str:
        """Run ripgrep search. Returns matched lines."""
        results = ContextEngine.rg_search(
            pattern, Path(workspace), max_results=50
        )
        if not results:
            return "No matches found."
        return "\n".join(results[:50])

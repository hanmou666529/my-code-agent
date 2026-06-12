"""Code-aware context engine using tree-sitter + ripgrep.

Builds a targeted "repomap"-style symbol index. Injects only relevant
context into the LLM prompt instead of dumping the entire codebase.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional

import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Query, QueryCursor


@dataclass
class Symbol:
    """A single symbol extracted from source code."""
    name: str
    kind: str  # "function", "class", "method", "import", "variable"
    file: Path
    line: int
    column: int = 0
    signature: str = ""
    docstring: Optional[str] = None
    body_snippet: str = ""  # first 5 lines of body


class ContextEngine:
    """AST + ripgrep code indexing engine."""

    # Precompiled tree-sitter query for Python symbols
    _PYTHON_QUERY = Query(
        Language(tspython.language()),
        """
        (function_definition
          name: (identifier) @func_name
          body: (block) @func_body)

        (class_definition
          name: (identifier) @class_name
          body: (block) @class_body)

        (import_statement
          name: (dotted_name) @import_name)
        """,
    )

    def __init__(self, workspace_root: Path) -> None:
        self._workspace = workspace_root.resolve()
        self._parser = Parser(Language(tspython.language()))
        self._symbols: List[Symbol] = []
        self._indexed_files: set[Path] = set()

    # ---- Indexing ----

    def index_file(self, file_path: Path) -> List[Symbol]:
        """Parse a single Python file and extract symbols."""
        if file_path.suffix != ".py":
            return []
        if file_path in self._indexed_files:
            return []

        try:
            source = file_path.read_bytes()
        except (OSError, PermissionError):
            return []

        tree = self._parser.parse(source)
        cursor = QueryCursor(self._PYTHON_QUERY)
        matches = cursor.matches(tree.root_node)

        symbols: List[Symbol] = []
        for _pattern_idx, captures in matches:
            # Group captures by their label
            by_label: dict[str, list] = {}
            for label, nodes in captures.items():
                by_label.setdefault(label, []).extend(nodes)

            if "func_name" in by_label:
                name_node = by_label["func_name"][0]
                func_name = name_node.text.decode()
                body_node = by_label.get("func_body", [None])[0]
                body_text = body_node.text.decode() if body_node else ""
                body_lines = body_text.split("\n")[:5]

                symbols.append(Symbol(
                    name=func_name,
                    kind="function",
                    file=file_path,
                    line=name_node.start_point[0] + 1,
                    column=name_node.start_point[1],
                    signature=func_name,
                    docstring=None,
                    body_snippet="\n".join(body_lines),
                ))

            if "class_name" in by_label:
                name_node = by_label["class_name"][0]
                class_body = by_label.get("class_body", [None])[0]
                symbols.append(Symbol(
                    name=name_node.text.decode(),
                    kind="class",
                    file=file_path,
                    line=name_node.start_point[0] + 1,
                    column=name_node.start_point[1],
                    docstring=None,
                    body_snippet=(
                        "\\n".join(class_body.text.decode().split("\\n")[:5])
                        if class_body else ""
                    ),
                ))

            if "import_name" in by_label:
                for imp_node in by_label["import_name"]:
                    symbols.append(Symbol(
                        name=imp_node.text.decode(),
                        kind="import",
                        file=file_path,
                        line=imp_node.start_point[0] + 1,
                    ))

        self._symbols.extend(symbols)
        self._indexed_files.add(file_path)
        return symbols

    def index_workspace(self, extensions: Optional[set[str]] = None) -> List[Symbol]:
        """Walk the workspace and index all Python files."""
        if extensions is None:
            extensions = {".py"}
        all_symbols: List[Symbol] = []
        for root, _dirs, files in self._workspace.walk():
            for fname in files:
                fpath = Path(root) / fname
                if fpath.suffix in extensions:
                    syms = self.index_file(fpath)
                    all_symbols.extend(syms)
        return all_symbols

    # ---- Querying ----

    def search_symbols(self, query_text: str) -> List[Symbol]:
        """Find symbols whose name or docstring matches the query (case-insensitive)."""
        q = query_text.lower()
        return [
            s for s in self._symbols
            if q in s.name.lower()
            or (s.docstring and q in s.docstring.lower())
        ]

    def get_file_context(
        self,
        file_path: Path,
        surrounding_lines: int = 20,
    ) -> str:
        """Return a file's content wrapped in XML tags with line numbers."""
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ""

        header = f'<file path="{file_path}">\n'
        footer = "</file>"
        start = max(0, len(lines) - surrounding_lines * 2)
        snippet = lines[start:]
        numbered = "\n".join(
            f"{start + i + 1:6d} | {line}" for i, line in enumerate(snippet)
        )
        return f"{header}\n{numbered}\n{footer}"

    # ---- Ripgrep integration ----

    @staticmethod
    def rg_search(pattern: str, workspace: Path, max_results: int = 50) -> List[str]:
        """Run ripgrep and return matching file:line pairs."""
        try:
            result = subprocess.run(
                ["rg", "-n", "--color", "never", "--no-heading",
                 "-F", pattern, str(workspace)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            lines = result.stdout.strip().split("\n")
            # Handle empty result
            if lines == [""]:
                return []
            return lines[:max_results]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

"""Tests for ContextEngine in context.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from my_code_agent.context import ContextEngine, Symbol


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with sample Python files."""
    # Create a sample Python file
    sample_py = tmp_path / "src" / "main.py"
    sample_py.parent.mkdir(parents=True, exist_ok=True)
    sample_py.write_text(
        '"""\nModule docstring.\n"""\n\n\ndef greet(name: str) -> str:\n'
        '    """Greet someone by name."""\n'
        '    return f"Hello, {name}!"\n\n\nclass Greeter:\n'
        '    """A class to greet people."""\n\n'
        "    def greet(self, name: str) -> str:\n"
        '        """Greet by instance."""\n'
        '        return f"Hi, {name}!"\n\n\n'
        "from os import path\n"
        "import sys\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def engine(workspace: Path) -> ContextEngine:
    """Create a ContextEngine with the sample workspace."""
    return ContextEngine(workspace)


class TestSymbol:
    def test_function_symbol_attributes(self) -> None:
        sym = Symbol(
            name="greet",
            kind="function",
            file=Path("main.py"),
            line=4,
            signature="greet(name: str) -> str",
            docstring='"""Greet someone by name."""',
        )
        assert sym.name == "greet"
        assert sym.kind == "function"
        assert sym.signature == "greet(name: str) -> str"


class TestContextEngine:
    def test_index_file_python(self, engine: ContextEngine, workspace: Path) -> None:
        py_file = workspace / "src" / "main.py"
        symbols = engine.index_file(py_file)

        names = [s.name for s in symbols]
        assert "greet" in names
        assert "Greeter" in names

    def test_index_file_non_python(self, engine: ContextEngine) -> None:
        # Non-Python files should return empty list
        symbols = engine.index_file(Path("readme.txt"))
        assert symbols == []

    def test_index_file_idempotent(self, engine: ContextEngine, workspace: Path) -> None:
        py_file = workspace / "src" / "main.py"
        first = engine.index_file(py_file)
        second = engine.index_file(py_file)
        assert len(second) == 0  # already indexed

    def test_index_workspace(self, engine: ContextEngine, workspace: Path) -> None:
        symbols = engine.index_workspace()
        assert len(symbols) > 0

    def test_search_symbols(self, engine: ContextEngine) -> None:
        engine.index_workspace()
        results = engine.search_symbols("greet")
        assert len(results) > 0
        # Should find functions and classes containing "greet"
        names = [s.name.lower() for s in results]
        assert any("greet" in name for name in names)

    def test_search_symbols_no_match(self, engine: ContextEngine) -> None:
        results = engine.search_symbols("xyznonexistent")
        assert results == []

    def test_get_file_context(self, engine: ContextEngine, workspace: Path) -> None:
        py_file = workspace / "src" / "main.py"
        context = engine.get_file_context(py_file)
        assert '<file path=' in context
        assert "</file>" in context
        assert "greet" in context

    def test_rgrep_search(self, engine: ContextEngine, workspace: Path) -> None:
        # rg_search may fail if ripgrep is not installed
        # Test that it handles the FileNotFoundError gracefully
        results = ContextEngine.rg_search(
            "nonexistent_pattern_12345", workspace, max_results=5
        )
        assert isinstance(results, list)

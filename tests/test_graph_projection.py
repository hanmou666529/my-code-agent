"""Unit tests for Graph Projection (CodebaseGraph)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from my_code_agent.graph_projection import CodebaseGraph, GraphEdge, GraphNode
from my_code_agent.semantic_tree import (
    DirectoryRole,
    WorkspaceStructureConfig,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a mini project with modules and imports."""
    src = tmp_path / "src"
    src.mkdir()

    # Module A
    mod_a = src / "module_a"
    mod_a.mkdir()
    (mod_a / "__init__.py").write_text("")
    (mod_a / "core.py").write_text("from src.module_b import helper\n")

    # Module B
    mod_b = src / "module_b"
    mod_b.mkdir()
    (mod_b / "__init__.py").write_text("")
    (mod_b / "utils.py").write_text("def helper(): pass\n")

    # Top-level file
    (src / "main.py").write_text("from src.module_a import core\n")

    return tmp_path


class TestGraphNodes:
    def test_graph_node_defaults(self) -> None:
        node = GraphNode(path=Path("test.py"))
        assert node.kind == "file"
        assert node.role == DirectoryRole.UNKNOWN
        assert node.metadata == {}

    def test_graph_edge_defaults(self) -> None:
        edge = GraphEdge(source=Path("a.py"), target=Path("b.py"))
        assert edge.edge_type == "import"
        assert edge.strength == 1.0

    def test_graph_node_with_metadata(self) -> None:
        node = GraphNode(
            path=Path("mod"),
            kind="module",
            role=DirectoryRole.DOMAIN_LOGIC,
            metadata={"file_count": 5},
        )
        assert node.kind == "module"
        assert node.role == DirectoryRole.DOMAIN_LOGIC
        assert node.metadata == {"file_count": 5}


class TestCodebaseGraphBuild:
    def test_build_physical(self, workspace: Path) -> None:
        config = WorkspaceStructureConfig.load(workspace)
        graph = CodebaseGraph(workspace, config)
        result = graph.build("physical")

        assert "nodes" in result
        assert "edges" in result
        assert len(result["nodes"]) > 0
        assert len(result["edges"]) > 0

        # Check node structure
        for node in result["nodes"]:
            assert "path" in node
            assert "kind" in node
            assert "role" in node

        # Check edge structure
        for edge in result["edges"]:
            assert "source" in edge
            assert "target" in edge
            assert "type" in edge

    def test_build_module(self, workspace: Path) -> None:
        config = WorkspaceStructureConfig.load(workspace)
        graph = CodebaseGraph(workspace, config)
        result = graph.build("module")

        assert "nodes" in result
        assert "edges" in result
        # Should have module nodes and file nodes
        kinds = {n["kind"] for n in result["nodes"]}
        assert "module" in kinds or "file" in kinds

    def test_build_dependency(self, workspace: Path) -> None:
        config = WorkspaceStructureConfig.load(workspace)
        graph = CodebaseGraph(workspace, config)
        result = graph.build("dependency")

        assert "nodes" in result
        assert "edges" in result
        # Should have import edges
        edge_types = {e["type"] for e in result["edges"]}
        assert "import" in edge_types

    def test_build_unknown_view(self, workspace: Path) -> None:
        config = WorkspaceStructureConfig.load(workspace)
        graph = CodebaseGraph(workspace, config)
        result = graph.build("nonexistent")
        assert result == {"error": "Unknown view: nonexistent"}

    def test_build_change(self, workspace: Path) -> None:
        """Change view should return changed files or empty list if no git."""
        config = WorkspaceStructureConfig.load(workspace)
        graph = CodebaseGraph(workspace, config)
        result = graph.build("change")
        # In a non-git temp dir, this returns empty but valid structure
        assert "nodes" in result
        assert "edges" in result


class TestCodebaseGraphQuery:
    def test_get_neighbors_empty(self, workspace: Path) -> None:
        config = WorkspaceStructureConfig.load(workspace)
        graph = CodebaseGraph(workspace, config)
        # Graph not built yet, no nodes registered
        neighbors = graph.get_neighbors(Path("nonexistent.py"))
        assert neighbors == []

    def test_find_cycles_empty(self, workspace: Path) -> None:
        config = WorkspaceStructureConfig.load(workspace)
        graph = CodebaseGraph(workspace, config)
        # No edges yet
        cycles = graph.find_cycles()
        assert cycles == []


class TestCodebaseGraphImportExtraction:
    def test_extract_imports_from_file(self, workspace: Path) -> None:
        config = WorkspaceStructureConfig.load(workspace)
        graph = CodebaseGraph(workspace, config)
        core_file = workspace / "src" / "module_a" / "core.py"
        imports = graph._extract_imports(core_file)
        # Should find the from import
        assert len(imports) >= 1
        assert any("module_b" in imp for imp in imports)

    def test_extract_imports_nonexistent(self, workspace: Path) -> None:
        config = WorkspaceStructureConfig.load(workspace)
        graph = CodebaseGraph(workspace, config)
        imports = graph._extract_imports(Path("/nonexistent/file.py"))
        assert imports == []

    @staticmethod
    def test_extract_imports_text() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fpath = Path(tmp) / "test.py"
            fpath.write_text(
                "import os\n"
                "from pathlib import Path\n"
                "from my_module import something\n"
            )
            imports = CodebaseGraph._extract_imports_text(fpath)
            assert "os" in imports
            assert "pathlib" in imports
            assert "my_module" in imports

    def test_resolve_single_import(self, workspace: Path) -> None:
        config = WorkspaceStructureConfig.load(workspace)
        graph = CodebaseGraph(workspace, config)
        mod_b = workspace / "src" / "module_b"
        resolved = graph._resolve_single_import("src.module_b", mod_b / "core.py")
        assert resolved is not None
        assert resolved == mod_b


class TestCodebaseGraphToDict:
    def test_to_dict_relativizes_paths(self, workspace: Path) -> None:
        config = WorkspaceStructureConfig.load(workspace)
        graph = CodebaseGraph(workspace, config)
        result = graph.build("physical")

        for node in result["nodes"]:
            # Paths should be relative to workspace
            assert not node["path"].startswith(str(workspace))

"""Graph Projection — multi-view dependency graph for the codebase.

Builds a directed acyclic graph (DAG) of the workspace using tree-sitter
for import-based dependency detection. Supports four views:

- **physical**: file/directory nodes + filesystem adjacency edges
- **module**: logical module nodes + containment edges
- **dependency**: module nodes + import edges (via tree-sitter)
- **change**: recently modified files + transitive dependency closure

Uses tree-sitter for Python import parsing as a replacement for madge
(which is Node.js-only).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Query, QueryCursor

from .semantic_tree import (
    DirectoryRole,
    DirectoryRole as _DR,
    SemanticTreeRenderer,
    SemanticTreeWalker,
    WorkspaceStructureConfig,
)


# ---------------------------------------------------------------------------
# Graph data model
# ---------------------------------------------------------------------------


@dataclass
class GraphEdge:
    """A single edge in the codebase graph."""

    source: Path
    target: Path
    edge_type: str = "import"  # "import", "contains", "changed_by"
    strength: float = 1.0


@dataclass
class GraphNode:
    """A single node in the codebase graph."""

    path: Path
    kind: str = "file"  # "file" or "module"
    role: DirectoryRole = DirectoryRole.UNKNOWN
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Import query for tree-sitter
# ---------------------------------------------------------------------------

_IMPORT_QUERY = Query(
    Language(tspython.language()),
    """
    (import_statement
      name: (dotted_name) @import_target)

    (import_from_statement
      module_name: (dotted_name) @from_module
      name: (dotted_name)? @import_name)

    (import_statement
      (aliased_import
        name: (dotted_name) @import_alias))
    """,
)


# ---------------------------------------------------------------------------
# CodebaseGraph
# ---------------------------------------------------------------------------


class CodebaseGraph:
    """Build and query multi-view dependency graphs."""

    def __init__(
        self,
        workspace_root: Path,
        config: Optional[WorkspaceStructureConfig] = None,
    ) -> None:
        self._workspace = workspace_root.resolve()
        self._config = config or WorkspaceStructureConfig.load(self._workspace)
        self._parser = Parser(Language(tspython.language()))
        self._nodes: dict[Path, GraphNode] = {}
        self._edges: list[GraphEdge] = []

    # ---- Public API ----

    def build(self, view: Literal["physical", "module", "dependency", "change"]) -> dict[str, Any]:
        """Build a graph view and return as a serializable dict."""
        builders = {
            "physical": self._build_physical,
            "module": self._build_module,
            "dependency": self._build_dependency,
            "change": self._build_change,
        }
        builder = builders.get(view)
        if builder is None:
            return {"error": f"Unknown view: {view}"}
        return builder()

    def get_neighbors(self, node_path: Path, view: str = "dependency") -> list[dict[str, Any]]:
        """Get neighboring nodes for a given node in a specific view."""
        resolved = node_path.resolve()
        node = self._nodes.get(resolved)
        if node is None:
            return []

        neighbors = []
        for edge in self._edges:
            if edge.source == resolved:
                target_node = self._nodes.get(edge.target)
                if target_node:
                    neighbors.append({
                        "path": str(edge.target),
                        "kind": target_node.kind,
                        "edge_type": edge.edge_type,
                    })
            elif edge.target == resolved:
                source_node = self._nodes.get(edge.source)
                if source_node:
                    neighbors.append({
                        "path": str(edge.source),
                        "kind": source_node.kind,
                        "edge_type": f"incoming_{edge.edge_type}",
                    })
        return neighbors

    def find_cycles(self) -> list[list[Path]]:
        """Find circular dependencies using DFS-based cycle detection."""
        adj: dict[Path, list[Path]] = {}
        for edge in self._edges:
            adj.setdefault(edge.source, []).append(edge.target)

        cycles: list[list[Path]] = []
        visited: set[Path] = set()
        rec_stack: set[Path] = set()

        def dfs(node: Path, path: list[Path]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])

            path.pop()
            rec_stack.discard(node)

        for node in list(self._nodes.keys()):
            if node not in visited:
                dfs(node, [])

        return cycles

    # ---- View builders ----

    def _build_physical(self) -> dict[str, Any]:
        """Physical view: all files and directories as nodes."""
        self._nodes.clear()
        self._edges.clear()

        walker = SemanticTreeWalker(self._workspace, self._config)
        root = walker.walk()
        self._populate_physical(root, "")
        return self._to_dict()

    def _populate_physical(self, node: "TreeNode", prefix: str) -> None:
        """Recursively populate physical view nodes and edges."""
        self._nodes[node.path] = GraphNode(
            path=node.path,
            kind="dir" if node.path.is_dir() else "file",
            role=node.role,
        )

        for child in node.children:
            self._edges.append(GraphEdge(
                source=node.path,
                target=child.path,
                edge_type="contains",
            ))
            self._populate_physical(child, prefix + node.path.name + "/")

        for f in node.files:
            self._nodes[f] = GraphNode(path=f, kind="file", role=DirectoryRole.UNKNOWN)
            self._edges.append(GraphEdge(
                source=node.path,
                target=f,
                edge_type="contains",
            ))

    def _build_module(self) -> dict[str, Any]:
        """Module view: logical modules as nodes with containment edges."""
        self._nodes.clear()
        self._edges.clear()

        # Find module roots (dirs with __init__.py or matching conventions)
        source_exts = {".py", ".ts", ".js", ".rs", ".go", ".java"}
        module_roots: list[Path] = []

        for root, dirs, files in self._workspace.walk():
            dirs[:] = [d for d in dirs if d not in self._config.ignore_patterns]
            if "__init__.py" in files or "index.py" in files:
                module_roots.append(root)

        # If no __init__.py found, use directories with 2+ source files
        if not module_roots:
            for root, dirs, files in self._workspace.walk():
                dirs[:] = [d for d in dirs if d not in self._config.ignore_patterns]
                src_count = sum(1 for f in files if Path(f).suffix in source_exts)
                if src_count >= 2:
                    module_roots.append(root)

        # Add module nodes
        for mod_root in module_roots:
            role = self._classify_module(mod_root)
            self._nodes[mod_root] = GraphNode(
                path=mod_root, kind="module", role=role,
                metadata={"file_count": sum(1 for _ in mod_root.rglob("*"))},
            )

        # Add file nodes and containment edges
        for mod_root in module_roots:
            for fpath in mod_root.rglob("*.py"):
                self._nodes[fpath] = GraphNode(path=fpath, kind="file")
                self._edges.append(GraphEdge(
                    source=mod_root, target=fpath, edge_type="contains",
                ))

        return self._to_dict()

    def _build_dependency(self) -> dict[str, Any]:
        """Dependency view: modules + import edges via tree-sitter."""
        self._nodes.clear()
        self._edges.clear()

        # Find module roots
        module_roots = self._find_module_roots()

        # Parse imports for each module
        for mod_root in module_roots:
            role = self._classify_module(mod_root)
            self._nodes[mod_root] = GraphNode(
                path=mod_root, kind="module", role=role,
            )

            for fpath in mod_root.rglob("*.py"):
                imports = self._extract_imports(fpath)
                for imp_target in imports:
                    # Try to resolve to another module root
                    resolved = self._resolve_import(imp_target, fpath, module_roots)
                    if resolved and resolved != mod_root:
                        self._edges.append(GraphEdge(
                            source=fpath, target=resolved, edge_type="import",
                        ))

        # Also add module-level dependency edges
        for mod_root in module_roots:
            deps: set[Path] = set()
            for fpath in mod_root.rglob("*.py"):
                imports = self._extract_imports(fpath)
                for imp_target in imports:
                    resolved = self._resolve_import(imp_target, fpath, module_roots)
                    if resolved:
                        deps.add(resolved)
            for dep in deps:
                if dep != mod_root:
                    self._edges.append(GraphEdge(
                        source=mod_root, target=dep, edge_type="import",
                        strength=0.5,
                    ))

        return self._to_dict()

    def _build_change(self) -> dict[str, Any]:
        """Change view: recently modified files + dependency closure."""
        self._nodes.clear()
        self._edges.clear()

        # Get recently modified files from git log (last 10 commits)
        changed_files = self._get_changed_files(limit=10)

        for fpath in changed_files:
            self._nodes[fpath] = GraphNode(path=fpath, kind="file", metadata={"changed": True})

        # Add dependency edges among changed files
        for f1 in changed_files:
            for f2 in changed_files:
                if f1 != f2:
                    # Check if f1 imports f2
                    imports = self._extract_imports(f1)
                    for imp in imports:
                        resolved = self._resolve_single_import(imp, f1)
                        if resolved and resolved in changed_files:
                            self._edges.append(GraphEdge(
                                source=f1, target=resolved, edge_type="changed_by",
                            ))

        return self._to_dict()

    # ---- Helpers ----

    def _find_module_roots(self) -> list[Path]:
        """Find module root directories."""
        source_exts = {".py", ".ts", ".js", ".rs", ".go", ".java"}
        roots: list[Path] = []

        for root, dirs, files in self._workspace.walk():
            dirs[:] = [d for d in dirs if d not in self._config.ignore_patterns]
            if "__init__.py" in files or "index.py" in files:
                roots.append(root)

        # Fallback: directories with 2+ source files
        if not roots:
            for root, dirs, files in self._workspace.walk():
                dirs[:] = [d for d in dirs if d not in self._config.ignore_patterns]
                src_count = sum(1 for f in files if Path(f).suffix in source_exts)
                if src_count >= 2:
                    roots.append(root)

        return roots

    def _classify_module(self, mod_root: Path) -> DirectoryRole:
        """Classify a module directory's role."""
        walker = SemanticTreeWalker(self._workspace, self._config)
        try:
            relative = mod_root.relative_to(self._workspace)
        except ValueError:
            relative = mod_root
        return walker._classify(mod_root, relative)

    def _extract_imports(self, file_path: Path) -> list[str]:
        """Extract import targets from a Python file using tree-sitter."""
        imports: list[str] = []
        try:
            source = file_path.read_bytes()
        except (OSError, PermissionError):
            return imports

        try:
            tree = self._parser.parse(source)
            cursor = QueryCursor(_IMPORT_QUERY)
            matches = cursor.matches(tree.root_node)
        except Exception:
            # Fallback to text-based parsing
            return self._extract_imports_text(file_path)

        for _pattern_idx, captures in matches.items() if isinstance(matches, dict) else matches:
            for label, nodes in captures.items():
                for node in nodes:
                    try:
                        text = node.text.decode()
                        imports.append(text.decode() if isinstance(text, bytes) else text)
                    except (AttributeError, UnicodeDecodeError):
                        pass

        return imports

    @staticmethod
    def _extract_imports_text(file_path: Path) -> list[str]:
        """Fallback text-based import extraction."""
        imports: list[str] = []
        try:
            text = file_path.read_text(errors="replace")
        except OSError:
            return imports

        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("from ") and " import " in stripped:
                target = stripped[5:].split(" import ")[0].strip()
                imports.append(target)
            elif stripped.startswith("import "):
                target = stripped[7:].split()[0]
                imports.append(target)
        return imports

    def _resolve_import(
        self,
        import_target: str,
        source_file: Path,
        module_roots: list[Path],
    ) -> Optional[Path]:
        """Resolve an import target to a module root path."""
        # Try resolving as absolute module path
        for mod_root in module_roots:
            mod_rel = str(mod_root.relative_to(self._workspace))
            if import_target == mod_rel or import_target.startswith(mod_rel + "."):
                return mod_root

        # Try resolving as relative import
        resolved = self._resolve_single_import(import_target, source_file)
        if resolved:
            return resolved

        return None

    def _resolve_single_import(
        self,
        import_target: str,
        source_file: Path,
    ) -> Optional[Path]:
        """Resolve a single import target to a file path."""
        parts = import_target.split(".")
        if not parts:
            return None

        # Try relative to source file's directory
        base = source_file.parent
        for part in parts:
            candidate = base / part
            if candidate.is_dir() and (candidate / "__init__.py").exists():
                return candidate
            if candidate.with_suffix(".py").is_file():
                return candidate.with_suffix(".py")
            base = candidate

        # Try relative to workspace
        candidate = self._workspace / "/".join(parts)
        if candidate.is_dir() and (candidate / "__init__.py").exists():
            return candidate
        if candidate.with_suffix(".py").is_file():
            return candidate.with_suffix(".py")

        return None

    def _get_changed_files(self, limit: int = 10) -> list[Path]:
        """Get recently changed files from git log."""
        try:
            result = subprocess.run(
                ["git", "log", f"--max-count={limit}", "--name-only",
                 "--format=", "--diff-filter=ACMR"],
                cwd=self._workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return []
            files = []
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line:
                    fpath = (self._workspace / line).resolve()
                    if fpath.is_file():
                        files.append(fpath)
            return files
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

    def _to_dict(self) -> dict[str, Any]:
        """Convert graph to a serializable dict."""
        nodes = []
        for path, node in self._nodes.items():
            try:
                rel = str(path.relative_to(self._workspace))
            except ValueError:
                rel = str(path)
            nodes.append({
                "path": rel,
                "kind": node.kind,
                "role": str(node.role),
                "metadata": node.metadata,
            })

        edges = []
        for edge in self._edges:
            try:
                src_rel = str(edge.source.relative_to(self._workspace))
                tgt_rel = str(edge.target.relative_to(self._workspace))
            except ValueError:
                src_rel = str(edge.source)
                tgt_rel = str(edge.target)
            edges.append({
                "source": src_rel,
                "target": tgt_rel,
                "type": edge.edge_type,
                "strength": edge.strength,
            })

        return {"nodes": nodes, "edges": edges}

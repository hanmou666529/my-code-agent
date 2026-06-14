"""MCP resource definitions for the coding agent.

Exposes the ContextEngine's functionality as MCP Resources, enabling
dynamic context loading instead of static system prompt injection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..context import ContextEngine
from ..dep_engine import FailureTracker
from ..dep_engine import UsageAnalytics as _UsageAnalytics
from ..graph_projection import CodebaseGraph
from ..semantic_tree import (
    SemanticTreeRenderer,
    SemanticTreeWalker,
    WorkspaceStructureConfig,
)


class ResourceRegistry:
    """Registry of MCP Resource handlers for the codebase."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace = workspace_root.resolve()
        self._engine = ContextEngine(workspace_root)

    def get_resource(self, uri: str) -> str:
        """Get a resource by URI.

        Supported URI schemes:
        - ``symbol://workspace/{file}?query={name}`` — search for symbols
        - ``context://file/{path}?lines={n}`` — get file context with line numbers
        - ``workspace://structure`` — semantic directory tree
        - ``workspace://structure?mode=summary`` — tree with 2 levels
        - ``workspace://structure?mode=full`` — full depth tree
        """
        if uri.startswith("symbol://"):
            return self._handle_symbol_resource(uri)
        elif uri.startswith("context://"):
            return self._handle_context_resource(uri)
        elif uri.startswith("workspace://"):
            return self._handle_workspace_resource(uri)
        elif uri.startswith("search://"):
            return self._handle_search_resource(uri)
        elif uri.startswith("tree://"):
            return self._handle_tree_resource(uri)
        elif uri.startswith("analytics://"):
            return self._handle_analytics_resource(uri)
        elif uri.startswith("failures://"):
            return self._handle_failures_resource(uri)
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

    def _handle_workspace_resource(self, uri: str) -> str:
        """Handle ``workspace://`` URIs.

        Parses mode parameter (``summary`` or ``full``) and renders
        the semantic directory tree.
        """
        mode: str = "summary"
        if "?mode=" in uri:
            try:
                mode = uri.split("mode=")[1].split("&")[0]
            except (IndexError, ValueError):
                pass

        config = WorkspaceStructureConfig.load(self._workspace)
        walker = SemanticTreeWalker(self._workspace, config)
        root = walker.walk()
        renderer = SemanticTreeRenderer(root, mode=mode)
        return renderer.render()

    def _handle_search_resource(self, uri: str) -> str:
        """Handle ``search://`` URIs for structural search.

        Examples:
        - search://?pattern=**/features/*
        - search://?pattern=*.py&role=domain-logic
        """
        from ..semantic_tree import DirectoryRole

        # Parse pattern and role from URI query string
        pattern = "*"
        role_str = ""
        if "?" in uri:
            query = uri.split("?", 1)[1]
            for param in query.split("&"):
                if "=" in param:
                    key, val = param.split("=", 1)
                    if key == "pattern":
                        pattern = val
                    elif key == "role":
                        role_str = val

        role: Optional[DirectoryRole] = None
        if role_str:
            try:
                role = DirectoryRole(role_str)
            except ValueError:
                pass

        return search_by_structure_fn(pattern, role, self._workspace)

    def _handle_tree_resource(self, uri: str) -> str:
        """Handle ``tree://`` URIs for multi-view graph queries.

        Examples:
        - tree://?view=dependency
        - tree://?view=dependency&focus=auth
        - tree://?view=physical
        - tree://?view=module
        - tree://?view=change&commits=10
        """
        view: str = "dependency"
        focus: str = ""
        commits: int = 10

        if "?" in uri:
            query = uri.split("?", 1)[1]
            for param in query.split("&"):
                if "=" in param:
                    key, val = param.split("=", 1)
                    if key == "view":
                        view = val
                    elif key == "focus":
                        focus = val
                    elif key == "commits":
                        try:
                            commits = int(val)
                        except ValueError:
                            pass

        config = WorkspaceStructureConfig.load(self._workspace)
        graph = CodebaseGraph(self._workspace, config)
        result = graph.build(view)

        # Apply focus filter if specified
        if focus and "nodes" in result:
            focused = [
                n for n in result["nodes"]
                if focus.lower() in n["path"].lower()
            ]
            node_paths = {n["path"] for n in focused}
            result["nodes"] = focused
            result["edges"] = [
                e for e in result["edges"]
                if e["source"] in node_paths or e["target"] in node_paths
            ]

        return str(result)

    def _handle_analytics_resource(self, uri: str) -> str:
        """Handle ``analytics://`` URIs for usage analytics.

        Examples:
        - analytics:// — full summary
        - analytics://?view=hotspots
        - analytics://?view=slow
        """
        view: str = "summary"
        if "?" in uri:
            query = uri.split("?", 1)[1]
            for param in query.split("&"):
                if "=" in param and param.split("=")[0] == "view":
                    view = param.split("=")[1]

        analytics = _UsageAnalytics(self._workspace)
        if view == "hotspots":
            return str(analytics.get_hotspots())
        elif view == "slow":
            return str(analytics.get_slow_tools())
        elif view == "underused":
            return str(analytics.get_underused_tools())
        return analytics.get_summary()

    def _handle_failures_resource(self, uri: str) -> str:
        """Handle ``failures://`` URIs for failure reports.

        Examples:
        - failures:// — full failure report
        - failures://?detail=suggestions
        """
        tracker = FailureTracker(self._workspace)
        report = tracker.get_failure_report()
        if "?" in uri and "detail=suggestions" in uri:
            suggestions = tracker.get_improvement_suggestions()
            if suggestions:
                report += "\n\nSuggestions:\n" + "\n".join(f"  - {s}" for s in suggestions)
        return report

    def list_resources(self) -> list[str]:
        """Return the list of available resource URIs."""
        return [
            "workspace://structure",
            "workspace://structure?mode=summary",
            "workspace://structure?mode=full",
            "search://",
            "search://?pattern=**/*",
            "search://?pattern=*.py&role=tests",
            "tree://",
            "tree://?view=physical",
            "tree://?view=module",
            "tree://?view=dependency",
            "tree://?view=change",
            "analytics://",
            "analytics://?view=hotspots",
            "analytics://?view=slow",
            "analytics://?view=underused",
            "failures://",
            "failures://?detail=suggestions",
            "symbol://workspace/",
            "context://file/",
        ]

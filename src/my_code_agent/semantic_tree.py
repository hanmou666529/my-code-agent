"""Semantic directory tree for workspace intelligence.

Builds a role-annotated directory tree from the workspace root.
Supports auto-inference of directory roles (domain-logic, infrastructure,
tests, interface-layer, feature) via naming heuristics and content analysis.

Outputs a compact tree with Unicode box-drawing characters and emoji,
suitable for CLI display and MCP resource delivery.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal, Optional

import yaml


# ---------------------------------------------------------------------------
# Enums and data classes
# ---------------------------------------------------------------------------


class DirectoryRole(Enum):
    """Semantic role of a directory within a project architecture."""

    DOMAIN_LOGIC = "domain-logic"
    INTERFACE_LAYER = "interface-layer"
    INFRASTRUCTURE = "infrastructure"
    TESTS = "tests"
    FEATURE = "feature"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value


@dataclass
class TreeNode:
    """A node in the semantic directory tree."""

    path: Path
    role: DirectoryRole = DirectoryRole.UNKNOWN
    children: list["TreeNode"] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_IGNORE_PATTERNS: list[str] = [
    ".git",
    "__pycache__",
    ".venv",
    "node_modules",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    "*.egg-info",
    ".cache",
    ".agent",
]

_DEFAULT_CONVENTIONS: dict[str, str] = {
    "feature_dirs": "features/*",
    "test_pattern": "tests/**",
    "source_prefix": "src",
}


@dataclass
class WorkspaceStructureConfig:
    """Parse and hold ``.agent/workspace-structure.yaml`` config."""

    version: str = "1"
    conventions: dict[str, str] = field(default_factory=dict)
    directory_roles: dict[str, DirectoryRole] = field(default_factory=dict)
    ignore_patterns: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, workspace_root: Path) -> WorkspaceStructureConfig:
        """Load config from ``workspace_root/.agent/workspace-structure.yaml``.

        Falls back to defaults if the file does not exist.
        """
        config_path = workspace_root / ".agent" / "workspace-structure.yaml"
        if not config_path.exists():
            return cls(
                conventions=dict(_DEFAULT_CONVENTIONS),
                ignore_patterns=list(_DEFAULT_IGNORE_PATTERNS),
            )

        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError):
            return cls(
                conventions=dict(_DEFAULT_CONVENTIONS),
                ignore_patterns=list(_DEFAULT_IGNORE_PATTERNS),
            )

        if not isinstance(raw, dict):
            raw = {}

        # Merge conventions with defaults
        conventions_raw = raw.get("conventions", {})
        conventions: dict[str, str] = dict(_DEFAULT_CONVENTIONS)
        if isinstance(conventions_raw, dict):
            conventions.update(conventions_raw)

        directory_roles_raw: dict[str, str] = raw.get("directory_roles", {})
        directory_roles: dict[str, DirectoryRole] = {}
        for k, v in directory_roles_raw.items():
            try:
                directory_roles[k] = DirectoryRole(v)
            except ValueError:
                pass

        # Merge ignore patterns with defaults
        ignore_patterns: list[str] = list(_DEFAULT_IGNORE_PATTERNS)
        raw_ignores = raw.get("ignore_patterns", [])
        if isinstance(raw_ignores, list):
            for extra in raw_ignores:
                if isinstance(extra, str) and extra not in ignore_patterns:
                    ignore_patterns.append(extra)

        return cls(
            version=str(raw.get("version", "1")),
            conventions=conventions,
            directory_roles=directory_roles,
            ignore_patterns=ignore_patterns,
        )

    def save(self, workspace_root: Path) -> None:
        """Write current config to ``.agent/workspace-structure.yaml``."""
        config_path = workspace_root / ".agent" / "workspace-structure.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.version,
            "conventions": self.conventions,
            "directory_roles": {
                k: v.value for k, v in self.directory_roles.items()
            },
            "ignore_patterns": [
                p for p in self.ignore_patterns
                if p not in _DEFAULT_IGNORE_PATTERNS
            ],
        }
        config_path.write_text(yaml.dump(payload, default_flow_style=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Naming heuristics
# ---------------------------------------------------------------------------

_INFRASTRUCTURE_NAMES: set[str] = {
    "mcp", "tools", "tui", "cli", "server", "utils", "lib",
    "common", "shared", "helpers", "middleware", "extensions",
}

_INTERFACE_LAYER_NAMES: set[str] = {
    "interface", "api", "routes", "handlers", "views", "controllers",
    "endpoints", "gateway", "adapter",
}

_DOMAIN_LOGIC_NAMES: set[str] = {
    "domain", "service", "use_case", "core", "models", "entities",
    "business", "logic", "application",
}

_TEST_NAMES: set[str] = {
    "tests", "test", "_tests",
}


def _classify_by_name(relative: Path) -> DirectoryRole | None:
    """Try to classify a directory purely by its name (relative path)."""
    parts = [p.lower() for p in relative.parts]
    dir_name = parts[-1] if parts else ""

    if dir_name in _TEST_NAMES:
        return DirectoryRole.TESTS

    if dir_name in _INFRASTRUCTURE_NAMES:
        return DirectoryRole.INFRASTRUCTURE

    if dir_name in _INTERFACE_LAYER_NAMES:
        return DirectoryRole.INTERFACE_LAYER

    if dir_name in _DOMAIN_LOGIC_NAMES:
        return DirectoryRole.DOMAIN_LOGIC

    # Check if any ancestor part matches domain logic names
    for part in parts[:-1]:
        if part in _DOMAIN_LOGIC_NAMES:
            return DirectoryRole.DOMAIN_LOGIC

    return None


# ---------------------------------------------------------------------------
# Content-based analysis
# ---------------------------------------------------------------------------

_SOURCE_EXTENSIONS: set[str] = {".py", ".ts", ".js", ".rs", ".go", ".java"}


def _classify_by_content(dir_path: Path) -> DirectoryRole:
    """Infer role from the files inside a directory."""
    source_files = [
        f for f in dir_path.iterdir()
        if f.is_file() and f.suffix in _SOURCE_EXTENSIONS
    ]
    if not source_files:
        return DirectoryRole.UNKNOWN

    py_files = [f for f in source_files if f.suffix == ".py"]
    if py_files:
        class_count = 0
        func_count = 0
        for pyf in py_files:
            try:
                text = pyf.read_text(errors="replace").lower()
                if "class " in text:
                    class_count += 1
                if "def " in text:
                    func_count += 1
            except OSError:
                continue

        # Many class defs → domain logic
        if class_count >= 2:
            return DirectoryRole.DOMAIN_LOGIC
        # Many functions, no classes → utility/infrastructure
        if func_count >= 3 and class_count == 0:
            return DirectoryRole.INFRASTRUCTURE

    return DirectoryRole.UNKNOWN


# ---------------------------------------------------------------------------
# Tree walker
# ---------------------------------------------------------------------------


class SemanticTreeWalker:
    """Walk the workspace, classify directories, build a semantic tree."""

    def __init__(
        self,
        workspace_root: Path,
        config: WorkspaceStructureConfig,
        max_depth: int = 10,
    ) -> None:
        self._workspace = workspace_root.resolve()
        self._config = config
        self._max_depth = max_depth

    # ---- Public API ----

    def walk(self) -> TreeNode:
        """Walk the workspace and return the root tree node."""
        return self._walk_dir(self._workspace, depth=0)

    def get_subtree(self, relative_path: str, depth: int = 2) -> TreeNode:
        """Build a subtree rooted at ``relative_path`` (relative to workspace)."""
        target = (self._workspace / relative_path).resolve()
        if not target.is_dir():
            return TreeNode(path=target, role=DirectoryRole.UNKNOWN)
        return self._walk_dir(target, depth=0, max_override=depth)

    # ---- Internal ----

    def _should_ignore(self, dirname: str) -> bool:
        """Check if a directory name matches ignore patterns."""
        if dirname in self._config.ignore_patterns:
            return True
        for pat in self._config.ignore_patterns:
            if "*" in pat and fnmatch.fnmatch(dirname, pat):
                return True
        return False

    def _classify(
        self, dir_path: Path, relative: Path
    ) -> DirectoryRole:
        """Classify a directory's role using a three-tier strategy."""
        # Tier 1: Explicit config override
        rel_str = str(relative)
        if rel_str in self._config.directory_roles:
            return self._config.directory_roles[rel_str]

        # Tier 2: Naming heuristics
        named = _classify_by_name(relative)
        if named is not None and named != DirectoryRole.UNKNOWN:
            return named

        # Tier 3: Content analysis
        try:
            if any(dir_path.iterdir()):
                return _classify_by_content(dir_path)
        except OSError:
            pass

        return DirectoryRole.UNKNOWN

    def _walk_dir(
        self,
        dir_path: Path,
        depth: int,
        max_override: Optional[int] = None,
    ) -> TreeNode:
        """Recursively walk a directory and build tree nodes."""
        if max_override is not None and depth >= max_override:
            return TreeNode(path=dir_path)

        if depth >= self._max_depth:
            return TreeNode(path=dir_path)

        relative = dir_path.relative_to(self._workspace)
        role = self._classify(dir_path, relative)

        node = TreeNode(path=dir_path, role=role)

        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return node

        for entry in entries:
            if entry.is_dir():
                if self._should_ignore(entry.name):
                    continue
                child = self._walk_dir(entry, depth + 1, max_override=max_override)
                # Include all non-ignored subdirectories (even empty ones — they are structural nodes)
                node.children.append(child)
            elif entry.is_file():
                node.files.append(entry)

        return node


# ---------------------------------------------------------------------------
# Tree renderer
# ---------------------------------------------------------------------------


class SemanticTreeRenderer:
    """Render a semantic tree to a Rich-compatible string."""

    # Box-drawing characters
    BRANCH = "├── "
    LAST_BRANCH = "└── "
    PIPE = "│   "
    SPACE = "    "

    DIR_ICON = "📁"
    FILE_ICON = "📄"

    def __init__(
        self,
        root: TreeNode,
        mode: Literal["summary", "full"] = "summary",
        max_depth: Optional[int] = None,
    ) -> None:
        self._root = root
        self._mode = mode
        self._max_depth = max_depth

    def render(self) -> str:
        """Render the tree to a string."""
        lines: list[str] = []
        self._render_node(self._root, "", True, 0, lines)
        return "\n".join(lines)

    def _render_node(
        self,
        node: TreeNode,
        prefix: str,
        is_last: bool,
        depth: int,
        lines: list[str],
    ) -> None:
        """Recursively render a tree node."""
        # Depth limit
        if self._max_depth is not None and depth > self._max_depth:
            return

        connector = self.LAST_BRANCH if not prefix else (self.BRANCH if not is_last else self.LAST_BRANCH)

        # Determine display name and role tag
        name = node.path.name if depth > 0 else str(node.path)
        role_tag = ""

        if node.role != DirectoryRole.UNKNOWN:
            if self._mode == "full":
                role_tag = f" [{node.role}]"
            elif self._mode == "summary" and depth <= 2:
                role_tag = f" [{node.role}]"

        if node.path.is_dir():
            icon = self.DIR_ICON
        else:
            icon = self.FILE_ICON

        lines.append(f"{prefix}{connector}{icon} {name}{role_tag}")

        if not node.path.is_dir():
            return

        child_prefix = prefix + (self.SPACE if is_last else self.PIPE)

        children_and_files: list[tuple[Path, bool]] = []
        for child in node.children:
            children_and_files.append((child.path, True))
        for f in node.files:
            children_and_files.append((f, True))

        # Only show first N children to keep output bounded
        max_children = 50
        if len(children_and_files) > max_children:
            children_and_files = children_and_files[:max_children]
            children_and_files[-1] = (
                node.path / "...",  # type: ignore[arg-type]
                True,
            )

        for idx, (child_path, _) in enumerate(children_and_files):
            is_last_child = (idx == len(children_and_files) - 1)

            if child_path.is_dir():
                # Find the corresponding TreeNode
                child_node = None
                for cn in node.children:
                    if cn.path == child_path:
                        child_node = cn
                        break
                if child_node is not None:
                    self._render_node(child_node, child_prefix, is_last_child, depth + 1, lines)
            else:
                # It's a file
                self._render_node(
                    TreeNode(path=child_path, role=DirectoryRole.UNKNOWN),
                    child_prefix,
                    is_last_child,
                    depth + 1,
                    lines,
                )

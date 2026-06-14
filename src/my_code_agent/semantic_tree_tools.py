"""Semantic tree tools for the coding agent.

Provides MCP tools for on-demand directory expansion, structural search,
and module boundary analysis.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Optional

from .semantic_tree import (
    DirectoryRole,
    SemanticTreeRenderer,
    SemanticTreeWalker,
    WorkspaceStructureConfig,
)


# ---------------------------------------------------------------------------
# Tool 1: expand_directory (enhanced)
# ---------------------------------------------------------------------------


def expand_directory(
    path: str,
    depth: int = 2,
    filter_ext: Optional[str] = None,
    include_files: bool = True,
    show_roles: bool = True,
    workspace_root: Optional[Path] = None,
) -> str:
    """Expand a specific directory with detailed contents.

    Args:
        path: Directory path relative to workspace root.
        depth: Number of subdirectory levels to expand (default 2).
        filter_ext: Optional file extension filter (e.g. ``".py"``).
        include_files: When False, only show directory structure.
        show_roles: Toggle ``[domain-logic]`` role tags.
        workspace_root: Workspace root (defaults to current directory).

    Returns:
        Rendered subtree as a string.
    """
    ws = (workspace_root or Path(".")).resolve()

    target = (ws / path).resolve()

    # Safety check: path must be within workspace
    try:
        target.relative_to(ws)
    except ValueError:
        return f"[SAFETY DENIED] Path escapes workspace: {target}"

    if not target.is_dir():
        return f"[ERROR] Not a directory: {target}"

    config = WorkspaceStructureConfig.load(ws)
    walker = SemanticTreeWalker(ws, config)
    subtree = walker.get_subtree(path, depth=depth)

    # Apply extension filter if specified
    if filter_ext:
        subtree.files = [f for f in subtree.files if f.suffix == filter_ext]

    # Hide files if requested
    if not include_files:
        subtree.files = []

    renderer = SemanticTreeRenderer(subtree, mode="full")
    # Temporarily hide role tags if disabled
    if not show_roles:
        renderer._mode = "summary"
    return renderer.render()


# ---------------------------------------------------------------------------
# Tool 2: search_by_structure
# ---------------------------------------------------------------------------


def search_by_structure(
    pattern: str,
    role: Optional[DirectoryRole] = None,
    workspace_root: Optional[Path] = None,
) -> str:
    """Search directories and files by structural pattern and optional role.

    Args:
        pattern: Glob-style pattern (e.g. ``"**/features/*"``, ``"*.py"``).
        role: Optional DirectoryRole to filter by (e.g. ``"domain-logic"``).
        workspace_root: Workspace root (defaults to current directory).

    Returns:
        Compact listing of matching paths with role annotations.
    """
    ws = (workspace_root or Path(".")).resolve()
    config = WorkspaceStructureConfig.load(ws)
    walker = SemanticTreeWalker(ws, config)
    root = walker.walk()

    matches: list[str] = []
    _search_node(root, pattern, role, "", matches)

    if not matches:
        return f"No matches for pattern ``{pattern}``" + (f" [role={role}]" if role else "")

    lines = [f"Found {len(matches)} match(es):"]
    lines.extend(matches)
    return "\n".join(lines)


def _search_node(
    node: "TreeNode",
    pattern: str,
    role: Optional[DirectoryRole],
    prefix: str,
    matches: list[str],
) -> None:
    """Recursively search tree nodes matching pattern and optional role."""
    rel_path = str(node.path.relative_to(
        Path(".").resolve()
    )) if node.path.is_relative_to(Path(".").resolve()) else str(node.path)

    # Check role filter
    if role is not None and node.role != role:
        # Check descendants for matching role
        has_matching_descendant = _has_role_descendant(node, role)
        if not has_matching_descendant:
            return

    # Check pattern against directory name
    if node.path.is_dir():
        dir_name = node.path.name
        if fnmatch.fnmatch(dir_name, pattern) or fnmatch.fnmatch(rel_path, pattern):
            tag = f" [{node.role}]" if node.role != DirectoryRole.UNKNOWN else ""
            matches.append(f"  📁 {rel_path}{tag}")

    # Check files in this directory
    if not node.path.is_dir():
        if fnmatch.fnmatch(node.path.name, pattern):
            matches.append(f"  📄 {rel_path}")

    # Recurse into children
    for child in node.children:
        child_prefix = prefix + node.path.name + "/" if prefix else node.path.name + "/"
        _search_node(child, pattern, role, child_prefix, matches)


def _has_role_descendant(node: "TreeNode", role: DirectoryRole) -> bool:
    """Check if any descendant has the given role."""
    if node.role == role:
        return True
    for child in node.children:
        if _has_role_descendant(child, role):
            return True
    return False


# ---------------------------------------------------------------------------
# Tool 3: get_module_boundary
# ---------------------------------------------------------------------------


def get_module_boundary(
    file_path: str,
    workspace_root: Optional[Path] = None,
) -> str:
    """Given a file, find its module boundary, dependencies, and dependents.

    Walks upward from the file to find the module root (first directory
    with ``__init__.py`` or matching ``feature_dirs`` convention), then
    analyzes imports to determine inter-module dependencies.

    Args:
        file_path: Path to the file (absolute or relative to workspace).
        workspace_root: Workspace root (defaults to current directory).

    Returns:
        Structured report of module boundary, files, and dependencies.
    """
    ws = (workspace_root or Path(".")).resolve()
    target = Path(file_path)
    if not target.is_absolute():
        target = ws / target
    target = target.resolve()

    if not target.is_file():
        return f"[ERROR] File not found: {target}"

    # Safety check
    try:
        target.relative_to(ws)
    except ValueError:
        return f"[SAFETY DENIED] Path escapes workspace: {target}"

    # Find module root by walking upward
    module_root = _find_module_root(target, ws)

    # Collect all source files in the module
    config = WorkspaceStructureConfig.load(ws)
    module_files = _collect_module_files(module_root, config)

    # Analyze imports for inter-module dependencies
    imports = _analyze_module_imports(module_files, ws)

    # Build report
    lines = [
        f"Module Boundary: {module_root.relative_to(ws)}",
        f"Role: {_infer_module_role(module_root, config)}",
        f"Files ({len(module_files)}):",
    ]
    for f in sorted(module_files):
        rel = f.relative_to(ws)
        lines.append(f"  📄 {rel}")

    if imports:
        lines.append("")
        lines.append("Dependencies:")
        for dep in sorted(imports):
            lines.append(f"  → {dep}")
    else:
        lines.append("")
        lines.append("Dependencies: none (internal module only)")

    return "\n".join(lines)


def _find_module_root(file_path: Path, workspace: Path) -> Path:
    """Find the module root by walking upward from the file.

    A module root is the first directory (starting from the file's parent)
    that contains ``__init__.py`` or matches the ``feature_dirs`` convention.
    Falls back to the nearest parent with source files.
    """
    current = file_path.parent
    workspace_resolved = workspace.resolve()

    while current != workspace_resolved and current != current.parent:
        # Check for __init__.py (Python package marker)
        if (current / "__init__.py").exists():
            return current
        # Check for index files (JS/TS convention)
        if (current / "index.py").exists() or (current / "index.ts").exists():
            return current
        current = current.parent

    return file_path.parent


def _collect_module_files(
    module_root: Path,
    config: WorkspaceStructureConfig,
) -> list[Path]:
    """Collect all source files within a module directory."""
    source_extensions = {".py", ".ts", ".js", ".rs", ".go", ".java"}
    files: list[Path] = []

    try:
        for root, dirs, filenames in module_root.walk():
            # Filter ignored directories
            dirs[:] = [
                d for d in dirs
                if d not in config.ignore_patterns
                and not any(fnmatch.fnmatch(d, p) for p in config.ignore_patterns if "*" in p)
            ]
            for fname in filenames:
                fpath = root / fname
                if fpath.suffix in source_extensions:
                    files.append(fpath)
    except OSError:
        pass

    return files


def _analyze_module_imports(
    module_files: list[Path],
    workspace: Path,
) -> list[str]:
    """Analyze imports across module files to find inter-module dependencies.

    Uses a simple text-based import parser (no tree-sitter overhead for
    this tool). Extracts module-level import targets and checks if they
    resolve to other directories in the workspace.
    """
    import_patterns: list[str] = []
    for fpath in module_files:
        if fpath.suffix != ".py":
            continue
        try:
            text = fpath.read_text(errors="replace")
        except OSError:
            continue

        for line in text.splitlines():
            stripped = line.strip()
            # Match: import foo.bar.baz
            if stripped.startswith("import "):
                parts = stripped[7:].split(",")
                for part in parts:
                    module_name = part.strip().split(" as ")[0].split()[0]
                    import_patterns.append(f"import:{module_name}")
            # Match: from foo.bar import baz
            elif stripped.startswith("from ") and " import " in stripped:
                module_name = stripped[5:].split(" import ")[0].strip()
                import_patterns.append(f"from:{module_name}")

    # Resolve import patterns to directory paths
    resolved: set[str] = set()
    try:
        for pattern in import_patterns:
            prefix, target = pattern.split(":", 1)
            # Try to resolve target to a workspace directory
            for root, dirs, _ in workspace.walk():
                for d in dirs:
                    if d == target or root.name == target:
                        resolved.add(f"{prefix}:{root}/{d}")
                        break
    except OSError:
        pass

    return sorted(resolved) if resolved else []


def _infer_module_role(
    module_root: Path,
    config: WorkspaceStructureConfig,
) -> str:
    """Infer the role of a module directory."""
    walker = SemanticTreeWalker(module_root, config)
    # Just classify the root directory
    relative = module_root.relative_to(module_root)  # = "."
    role = walker._classify(module_root, relative)
    return str(role) if role != DirectoryRole.UNKNOWN else "unknown"

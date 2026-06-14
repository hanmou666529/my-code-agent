"""Convention Learner v2 — auto-infer project conventions.

Analyzes the workspace file distribution, naming patterns, and import
relationships to automatically infer project conventions such as
feature_dirs, test_pattern, source_prefix, and directory_roles.

Output is written to ``.agent/inferred-conventions.yaml`` and can be
merged into ``.agent/workspace-structure.yaml`` via ``apply_inferred()``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from .semantic_tree import (
    DirectoryRole,
    SemanticTreeWalker,
    WorkspaceStructureConfig,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class InferenceResult:
    """Container for convention inference results."""

    feature_dirs: list[str] = field(default_factory=list)
    test_pattern: str = "tests/**"
    source_prefix: str = "src"
    directory_roles: dict[str, DirectoryRole] = field(default_factory=dict)
    import_patterns: dict[str, list[str]] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Learner
# ---------------------------------------------------------------------------


class ConventionLearner:
    """Auto-infer project conventions from workspace structure."""

    def __init__(self, workspace_root: Path) -> None:
        self._workspace = workspace_root.resolve()
        self._config = WorkspaceStructureConfig.load(self._workspace)

    # ---- Public API ----

    def learn(self) -> InferenceResult:
        """Run all inference passes and return combined results."""
        result = InferenceResult()
        result.feature_dirs = self.learn_feature_dirs()
        result.test_pattern = self.learn_test_pattern()
        result.source_prefix = self.learn_source_prefix()
        result.directory_roles = self.learn_directory_roles()
        result.import_patterns = self.learn_import_patterns()
        result.confidence = self._compute_confidence(result)
        return result

    def learn_feature_dirs(self) -> list[str]:
        """Find directories that look like feature containers.

        A feature directory has 2+ subdirectories, each containing
        source files, and shares a common parent.
        """
        source_exts = {".py", ".ts", ".js", ".rs", ".go", ".java"}
        candidates: dict[Path, list[Path]] = {}

        for root, dirs, files in self._workspace.walk():
            # Skip ignored dirs
            dirs[:] = [
                d for d in dirs
                if d not in self._config.ignore_patterns
            ]
            if not files:
                continue

            # Check if this dir has source files
            src_files = [f for f in files if Path(f).suffix in source_exts]
            if len(src_files) >= 2:
                # This dir looks like a feature — collect its parent
                parent = root
                candidates.setdefault(parent, []).extend(src_files)

        # Group by parent and find parents with multiple feature children
        feature_parents: dict[Path, int] = Counter()
        for parent, files in candidates.items():
            feature_parents[parent] += len(files)

        # Return parents that have significant source activity
        feature_dirs = []
        for parent, count in feature_parents.most_common():
            if count >= 3:
                rel = parent.relative_to(self._workspace)
                feature_dirs.append(str(rel))

        return feature_dirs[:10]  # Top 10

    def learn_test_pattern(self) -> str:
        """Infer test file naming convention and directory pattern."""
        test_files: list[Path] = []
        test_dirs: Counter = Counter()

        for root, dirs, files in self._workspace.walk():
            dirs[:] = [d for d in dirs if d not in self._config.ignore_patterns]
            for fname in files:
                fpath = root / fname
                if re.match(r"(test_|_test\.|tests?/)", fname, re.IGNORECASE):
                    test_files.append(fpath)
                    test_dirs[root.name] += 1

        if not test_files:
            return "tests/**"

        # Determine the most common test directory
        if test_dirs:
            top_dir = test_dirs.most_common(1)[0][0]
            return f"{top_dir}/**"

        # Fall back to naming pattern
        naming = "test_*.py" if any(f.name.startswith("test_") for f in test_files) else "*_test.py"
        return f"**/{naming}"

    def learn_source_prefix(self) -> str:
        """Infer the source code prefix directory (e.g. 'src', 'lib')."""
        source_exts = {".py", ".ts", ".js", ".rs", ".go", ".java"}
        source_dirs: Counter = Counter()

        for root, dirs, files in self._workspace.walk():
            dirs[:] = [d for d in dirs if d not in self._config.ignore_patterns]
            src_count = sum(1 for f in files if Path(f).suffix in source_exts)
            if src_count > 0:
                # Depth from workspace root
                depth = len(root.relative_to(self._workspace).parts)
                source_dirs[depth] += src_count

        if not source_dirs:
            return "src"

        # Shallowest depth with significant source files
        min_depth = min(source_dirs.keys())
        # Find the actual directory name at that depth
        for root, dirs, files in self._workspace.walk():
            dirs[:] = [d for d in dirs if d not in self._config.ignore_patterns]
            depth = len(root.relative_to(self._workspace).parts)
            if depth == min_depth:
                src_count = sum(1 for f in files if Path(f).suffix in source_exts)
                if src_count >= 2:
                    return str(root.relative_to(self._workspace))

        return "src"

    def learn_directory_roles(self) -> dict[str, DirectoryRole]:
        """Run the existing three-tier classifier on all directories."""
        walker = SemanticTreeWalker(self._workspace, self._config)
        root = walker.walk()
        roles: dict[str, DirectoryRole] = {}

        for node in self._flatten_tree(root):
            if node.role != DirectoryRole.UNKNOWN:
                rel = str(node.path.relative_to(self._workspace))
                roles[rel] = node.role

        return roles

    def learn_import_patterns(self) -> dict[str, list[str]]:
        """Analyze import relationships between modules.

        Returns a mapping of module_dir → [imported_module_dirs].
        """
        source_exts = {".py"}
        module_roots: list[Path] = []

        # Find module roots (dirs with __init__.py)
        for root, dirs, files in self._workspace.walk():
            dirs[:] = [d for d in dirs if d not in self._config.ignore_patterns]
            if "__init__.py" in files:
                module_roots.append(root)

        patterns: dict[str, list[str]] = {}
        for mod_root in module_roots:
            mod_rel = str(mod_root.relative_to(self._workspace))
            imports: set[str] = set()

            for fpath in mod_root.rglob("*.py"):
                try:
                    text = fpath.read_text(errors="replace")
                except OSError:
                    continue

                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("from ") and " import " in stripped:
                        target = stripped[5:].split(" import ")[0].strip()
                        # Check if target matches any module root
                        for mr in module_roots:
                            mr_rel = str(mr.relative_to(self._workspace))
                            if target == mr_rel or target.startswith(mr_rel + "."):
                                imports.add(mr_rel)
                    elif stripped.startswith("import "):
                        target = stripped[7:].split()[0]
                        for mr in module_roots:
                            mr_rel = str(mr.relative_to(self._workspace))
                            if target == mr_rel or target.startswith(mr_rel + "."):
                                imports.add(mr_rel)

            if imports:
                patterns[mod_rel] = sorted(imports)

        return patterns

    # ---- Confidence computation ----

    def _compute_confidence(self, result: InferenceResult) -> dict[str, float]:
        """Compute confidence scores for each inferred convention."""
        confidence: dict[str, float] = {}

        # feature_dirs: high if we found multiple candidates
        confidence["feature_dirs"] = min(0.95, 0.5 + len(result.feature_dirs) * 0.1)

        # test_pattern: high if we found test files
        test_count = sum(
            1 for _ in self._workspace.glob("**/test_*.py")
        )
        confidence["test_pattern"] = min(0.95, 0.6 + test_count * 0.05)

        # source_prefix: very high (structural invariant)
        confidence["source_prefix"] = 0.99

        # directory_roles: moderate (heuristic-based)
        confidence["directory_roles"] = 0.75 if result.directory_roles else 0.0

        # import_patterns: moderate
        confidence["import_patterns"] = (
            0.7 if result.import_patterns else 0.0
        )

        return confidence

    # ---- Persistence ----

    def infer_and_save(
        self,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Run inference and save to YAML file.

        Returns the path where the file was written.
        """
        result = self.learn()
        if output_path is None:
            output_path = self._workspace / ".agent" / "inferred-conventions.yaml"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "1",
            "inferred_at": "auto",
            "conventions": {
                "feature_dirs": result.feature_dirs,
                "test_pattern": result.test_pattern,
                "source_prefix": result.source_prefix,
            },
            "directory_roles": {
                k: v.value for k, v in result.directory_roles.items()
            },
            "import_patterns": result.import_patterns,
            "confidence": {
                k: round(v, 2) for k, v in result.confidence.items()
            },
        }
        output_path.write_text(
            yaml.dump(payload, default_flow_style=False), encoding="utf-8"
        )
        return output_path

    @staticmethod
    def apply_inferred(workspace_root: Path) -> None:
        """Merge inferred conventions into workspace-structure.yaml."""
        inferred_path = workspace_root / ".agent" / "inferred-conventions.yaml"
        if not inferred_path.exists():
            print("No inferred conventions found. Run infer_and_save() first.")
            return

        raw = yaml.safe_load(inferred_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return

        # Load existing config
        config_path = workspace_root / ".agent" / "workspace-structure.yaml"
        existing = {}
        if config_path.exists():
            try:
                existing = yaml.safe_load(
                    config_path.read_text(encoding="utf-8")
                ) or {}
            except yaml.YAMLError:
                existing = {}

        if not isinstance(existing, dict):
            existing = {}

        # Merge conventions
        conventions = existing.get("conventions", {})
        if isinstance(conventions, dict):
            conventions.update(raw.get("conventions", {}))
            existing["conventions"] = conventions

        # Merge directory_roles
        roles = existing.get("directory_roles", {})
        if isinstance(roles, dict):
            roles.update(raw.get("directory_roles", {}))
            existing["directory_roles"] = roles

        config_path.write_text(
            yaml.dump(existing, default_flow_style=False), encoding="utf-8"
        )

    # ---- Helpers ----

    @staticmethod
    def _flatten_tree(node: "TreeNode") -> list["TreeNode"]:
        """Flatten a tree into a list of all nodes."""
        result = [node]
        for child in node.children:
            result.extend(ConventionLearner._flatten_tree(child))
        return result

"""Unit tests for the semantic directory tree system."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from my_code_agent.semantic_tree import (
    DirectoryRole,
    SemanticTreeRenderer,
    SemanticTreeWalker,
    WorkspaceStructureConfig,
    _classify_by_content,
    _classify_by_name,
)


class TestDirectoryRoleNaming(TestCase):
    """Test classification by directory name."""

    def test_test_names(self) -> None:
        self.assertEqual(_classify_by_name(Path("tests")), DirectoryRole.TESTS)
        self.assertEqual(_classify_by_name(Path("test")), DirectoryRole.TESTS)
        self.assertEqual(_classify_by_name(Path("_tests")), DirectoryRole.TESTS)

    def test_infrastructure_names(self) -> None:
        for name in ["mcp", "tools", "tui", "cli", "server", "utils", "lib"]:
            self.assertEqual(
                _classify_by_name(Path(name)),
                DirectoryRole.INFRASTRUCTURE,
                f"Expected {name} to be INFRASTRUCTURE",
            )

    def test_interface_layer_names(self) -> None:
        for name in ["interface", "api", "routes", "handlers", "views"]:
            self.assertEqual(
                _classify_by_name(Path(name)),
                DirectoryRole.INTERFACE_LAYER,
                f"Expected {name} to be INTERFACE_LAYER",
            )

    def test_domain_logic_names(self) -> None:
        for name in ["domain", "service", "use_case", "core", "models"]:
            result = _classify_by_name(Path(name))
            self.assertIn(
                result,
                {DirectoryRole.DOMAIN_LOGIC, DirectoryRole.INFRASTRUCTURE},
                f"Expected {name} to be DOMAIN_LOGIC or INFRASTRUCTURE, got {result}",
            )

    def test_unknown_name(self) -> None:
        self.assertIsNone(_classify_by_name(Path("random")))
        self.assertIsNone(_classify_by_name(Path("foo/bar/baz")))


class TestConfigLoadSave(TestCase):
    """Test WorkspaceStructureConfig load/save."""

    def test_load_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            config = WorkspaceStructureConfig.load(ws)
            self.assertEqual(config.version, "1")
            self.assertIn("feature_dirs", config.conventions)
            self.assertIn(".git", config.ignore_patterns)

    def test_load_custom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            config_dir = ws / ".agent"
            config_dir.mkdir()
            yaml_content = """\
version: "2"
conventions:
  feature_dirs: "modules/*"
directory_roles:
  "custom_dir": "infrastructure"
ignore_patterns:
  - "custom_ignore"
"""
            (config_dir / "workspace-structure.yaml").write_text(yaml_content)
            config = WorkspaceStructureConfig.load(ws)
            self.assertEqual(config.version, "2")
            self.assertEqual(config.conventions["feature_dirs"], "modules/*")
            self.assertEqual(
                config.directory_roles["custom_dir"], DirectoryRole.INFRASTRUCTURE
            )
            self.assertIn("custom_ignore", config.ignore_patterns)

    def test_save_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            config = WorkspaceStructureConfig.load(ws)
            config.conventions["feature_dirs"] = "pkg/*"
            config.save(ws)
            reloaded = WorkspaceStructureConfig.load(ws)
            self.assertEqual(reloaded.conventions["feature_dirs"], "pkg/*")


class TestTreeWalker(TestCase):
    """Test SemanticTreeWalker."""

    def test_walk_filters_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            # Create a mini project
            (ws / "src").mkdir()
            (ws / "src" / "main.py").write_text("class Foo: pass\n")
            (ws / "tests").mkdir()
            (ws / "tests" / "test_main.py").write_text("def test_foo(): pass\n")
            (ws / ".git").mkdir()
            (ws / "__pycache__").mkdir()

            config = WorkspaceStructureConfig.load(ws)
            walker = SemanticTreeWalker(ws, config)
            root = walker.walk()

            # Noise dirs should be filtered
            dir_names = [c.path.name for c in root.children]
            self.assertNotIn(".git", dir_names)
            self.assertNotIn("__pycache__", dir_names)
            self.assertIn("src", dir_names)
            self.assertIn("tests", dir_names)

    def test_classify_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "tests").mkdir()
            config = WorkspaceStructureConfig.load(ws)
            walker = SemanticTreeWalker(ws, config)
            root = walker.walk()
            tests_dir = next(
                (c for c in root.children if c.path.name == "tests"), None
            )
            self.assertIsNotNone(tests_dir)
            self.assertEqual(tests_dir.role, DirectoryRole.TESTS)

    def test_max_depth_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            deep = ws / "a" / "b" / "c" / "d"
            deep.mkdir(parents=True)
            (deep / "file.txt").write_text("x")
            config = WorkspaceStructureConfig.load(ws)
            walker = SemanticTreeWalker(ws, config, max_depth=2)
            root = walker.walk()
            # Should not go deeper than 2 levels
            self.assertTrue(
                all(c.path.relative_to(ws).parts and len(c.path.relative_to(ws).parts) <= 2 for c in root.children)
            )


class TestTreeRenderer(TestCase):
    """Test SemanticTreeRenderer."""

    def test_render_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "src").mkdir()
            (ws / "src" / "main.py").write_text("pass\n")
            (ws / "tests").mkdir()
            (ws / "tests" / "test_main.py").write_text("pass\n")

            config = WorkspaceStructureConfig.load(ws)
            walker = SemanticTreeWalker(ws, config)
            root = walker.walk()
            renderer = SemanticTreeRenderer(root, mode="summary")
            output = renderer.render()

            self.assertIn("src", output)
            self.assertIn("tests", output)
            self.assertIn("main.py", output)
            self.assertIn("├──", output)
            self.assertIn("└──", output)

    def test_render_full(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "src").mkdir()
            (ws / "src" / "main.py").write_text("pass\n")

            config = WorkspaceStructureConfig.load(ws)
            walker = SemanticTreeWalker(ws, config)
            root = walker.walk()
            renderer = SemanticTreeRenderer(root, mode="full")
            output = renderer.render()

            self.assertIn("main.py", output)

    def test_render_with_role_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "tests").mkdir()
            (ws / "tests" / "test_x.py").write_text("pass\n")

            config = WorkspaceStructureConfig.load(ws)
            walker = SemanticTreeWalker(ws, config)
            root = walker.walk()
            renderer = SemanticTreeRenderer(root, mode="summary")
            output = renderer.render()

            # tests dir should have role tag
            self.assertIn("[tests]", output)


class TestExpandDirectory(TestCase):
    """Test expand_directory tool."""

    def test_expand_basic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "src").mkdir()
            (ws / "src" / "main.py").write_text("pass\n")
            (ws / "src" / "utils.py").write_text("pass\n")

            from my_code_agent.semantic_tree_tools import expand_directory
            output = expand_directory("src", depth=1, workspace_root=ws)
            self.assertIn("main.py", output)
            self.assertIn("utils.py", output)

    def test_expand_escapes_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            from my_code_agent.semantic_tree_tools import expand_directory
            output = expand_directory("../outside", workspace_root=ws)
            self.assertIn("SAFETY DENIED", output)

    def test_expand_nonexistent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            from my_code_agent.semantic_tree_tools import expand_directory
            output = expand_directory("nonexistent", workspace_root=ws)
            self.assertIn("ERROR", output)


class TestResourceRegistry(TestCase):
    """Test ResourceRegistry workspace://resource."""

    def test_workspace_resource(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "src").mkdir()
            (ws / "src" / "main.py").write_text("pass\n")
            (ws / "tests").mkdir()

            from my_code_agent.mcp.resources import ResourceRegistry
            reg = ResourceRegistry(ws)
            output = reg.get_resource("workspace://structure?mode=summary")
            self.assertIn("src", output)
            self.assertIn("tests", output)

    def test_list_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            from my_code_agent.mcp.resources import ResourceRegistry
            reg = ResourceRegistry(ws)
            resources = reg.list_resources()
            self.assertIn("workspace://structure", resources)
            self.assertIn("workspace://structure?mode=summary", resources)
            self.assertIn("workspace://structure?mode=full", resources)


if __name__ == "__main__":
    import unittest
    unittest.main()

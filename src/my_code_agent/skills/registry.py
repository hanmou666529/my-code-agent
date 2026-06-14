"""Skill Registry — discovery, loading, and hot reload.

Scans a skills directory for ``.skill.md`` files, falls back to the
legacy ``skills.json`` format, and provides a unified interface for
skill lookup with mtime-based hot reload detection.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .models import SkillDefinition, SkillLevel
from .parser import parse_old_skill_json, parse_skill_file


class SkillRegistry:
    """Central skill discovery and loading with hot reload support."""

    def __init__(
        self,
        workspace_root: Path,
        skills_dir: Optional[Path] = None,
        skills_json_path: Optional[Path] = None,
    ) -> None:
        self._workspace = workspace_root.resolve()
        self._skills_dir = (skills_dir or self._workspace / ".agent" / "skills").resolve()
        self._skills_json_path = (
            skills_json_path or self._workspace / ".mcp" / "skills.json"
        ).resolve()
        self._skills: Dict[str, SkillDefinition] = {}
        self._mtimes: Dict[str, float] = {}

    # ---- Public API ----

    def load(self) -> None:
        """Load all skills from disk.

        Priority: .skill.md files > legacy skills.json.
        If a skill exists in both formats, the .skill.md version wins.
        """
        self._skills.clear()
        self._mtimes.clear()

        # Load .skill.md files first
        self._load_skill_md_files()

        # Then load legacy skills.json (backward compat)
        self._load_legacy_json()

    def get_skill(self, name: str) -> Optional[SkillDefinition]:
        """Get a skill by name, or None if not found."""
        return self._skills.get(name)

    def list_skills(self) -> list[str]:
        """Return the list of registered skill names."""
        return list(self._skills.keys())

    def has_skill(self, name: str) -> bool:
        """Check if a skill is registered."""
        return name in self._skills

    def all_skills(self) -> Dict[str, SkillDefinition]:
        """Return all registered skills."""
        return dict(self._skills)

    def has_changed(self) -> bool:
        """Check if any skill file has changed since last load."""
        current_mtimes = self._collect_current_mtis()
        if current_mtimes != self._mtimes:
            return True
        return False

    def reload(self) -> None:
        """Reload skills if files have changed."""
        if self.has_changed():
            self.load()
            return True
        return False

    def watch_loop(self, callback: Optional[Callable[[], None]] = None) -> None:
        """Background daemon thread that polls for file changes.

        Runs indefinitely; set daemon=True so it doesn't block exit.
        Calls callback (if provided) after each reload.
        """
        def _loop() -> None:
            while True:
                time.sleep(2)
                if self.has_changed():
                    self.load()
                    if callback:
                        callback()

        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    # ---- Internal ----

    def _load_skill_md_files(self) -> None:
        """Scan skills_dir for .skill.md files."""
        if not self._skills_dir.exists():
            return

        for path in sorted(self._skills_dir.glob("*.skill.md")):
            try:
                skill = parse_skill_file(path)
                self._skills[skill.name] = skill
                self._mtimes[path.name] = path.stat().st_mtime
            except (ValueError, OSError) as e:
                # Log parse error but don't crash the registry
                self._skills[skill.name if 'skill' in dir() else f"parse_error_{path.name}"] = (
                    SkillDefinition(
                        name=f"parse_error_{path.name}",
                        version="0.0",
                        level=SkillLevel.L0,
                        description=f"Parse error: {e}",
                        type_signature=None,  # type: ignore[arg-type]
                    )
                )

    def _load_legacy_json(self) -> None:
        """Load legacy skills.json entries as fallback."""
        if not self._skills_json_path.exists():
            return

        try:
            data = json.loads(
                self._skills_json_path.read_text(encoding="utf-8")
            )
            if not isinstance(data, list):
                return

            mtime = self._skills_json_path.stat().st_mtime
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name", "")
                if not name:
                    continue
                # Only load if not already overridden by .skill.md
                if name not in self._skills:
                    try:
                        skill = parse_old_skill_json(entry)
                        self._skills[name] = skill
                        self._mtimes[name + ".json"] = mtime
                    except (KeyError, TypeError):
                        pass
        except (json.JSONDecodeError, OSError):
            pass

    def _collect_current_mtis(self) -> Dict[str, float]:
        """Collect current mtime dict for change detection."""
        mtimes: Dict[str, float] = {}
        if self._skills_dir.exists():
            for path in self._skills_dir.glob("*.skill.md"):
                mtimes[path.name] = path.stat().st_mtime
        if self._skills_json_path.exists():
            mtimes["skills.json"] = self._skills_json_path.stat().st_mtime
        return mtimes

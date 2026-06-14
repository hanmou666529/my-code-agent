"""HumanReview — directory-based skill review workflow.

Manages the PR-style review process: drafts that pass the eval gate
are queued for human review, then approved (published) or rejected
with feedback.

Directory layout:
    .agent/skills/drafts/          — drafts awaiting eval
    .agent/skills/pending_review/  — passed eval, awaiting human
    .agent/skills/                  — published skills (SkillRegistry watches)
    .agent/skills/rejected/         — rejected drafts
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .models import DraftStatus, SkillDraft


class HumanReview:
    """Manages the human review workflow for drafted skills."""

    def __init__(
        self,
        workspace_root: Path,
        pending_dir: Optional[Path] = None,
        published_dir: Optional[Path] = None,
        rejected_dir: Optional[Path] = None,
    ) -> None:
        self._workspace = workspace_root.resolve()
        self._base = self._workspace / ".agent" / "skills"
        self._drafts_dir = self._base / "drafts"
        self._pending_dir = pending_dir or (self._base / "pending_review")
        self._published_dir = published_dir or self._base
        self._rejected_dir = rejected_dir or (self._base / "rejected")

    # ---- Public API ----

    def queue_for_review(self, draft: SkillDraft) -> Path:
        """Queue a draft for human review.

        Moves (copies) the draft's .skill.md file to the pending_review
        directory.

        Returns the path to the queued file.
        """
        self._pending_dir.mkdir(parents=True, exist_ok=True)

        # Write the skill file to pending_review
        file_path = self._pending_dir / f"{draft.draft_id}.skill.md"
        file_path.write_text(draft.skill_md_content, encoding="utf-8")

        return file_path

    def approve(self, draft: SkillDraft) -> Path:
        """Approve a draft and publish it.

        Moves the skill to the published directory (`.agent/skills/`),
        where the SkillRegistry will auto-discover it.

        Returns the path to the published file.
        """
        self._published_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._published_dir / f"{draft.draft_id}.skill.md"
        file_path.write_text(draft.skill_md_content, encoding="utf-8")

        return file_path

    def reject(self, draft: SkillDraft, feedback: str) -> Path:
        """Reject a draft with feedback.

        Moves the skill to the rejected directory.

        Returns the path to the rejected file.
        """
        self._rejected_dir.mkdir(parents=True, exist_ok=True)

        file_path = self._rejected_dir / f"{draft.draft_id}.skill.md"
        file_path.write_text(draft.skill_md_content, encoding="utf-8")

        return file_path

    def list_pending(self) -> list[SkillDraft]:
        """List all pending (queued for review) drafts.

        Returns SkillDraft objects with the file path resolved.
        """
        if not self._pending_dir.exists():
            return []

        drafts: list[SkillDraft] = []
        for path in sorted(self._pending_dir.glob("*.skill.md")):
            content = path.read_text(encoding="utf-8")
            # stem gives "draft-1.skill" for "draft-1.skill.md"
            draft_id = path.stem.rsplit(".", 1)[0] if "." in path.stem else path.stem
            drafts.append(SkillDraft(
                draft_id=draft_id,
                skill_md_content=content,
                status=DraftStatus.PENDING_REVIEW,
            ))
        return drafts

    def generate_review_diff(self, draft: SkillDraft) -> str:
        """Generate a human-readable review output for a draft.

        Shows the key fields extracted from the .skill.md content.
        """
        import re

        # Extract YAML frontmatter
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*", draft.skill_md_content, re.DOTALL)
        if not fm_match:
            return "[ERROR] Could not parse draft frontmatter"

        # Simple YAML-like parsing (enough for review display)
        lines = fm_match.group(1).split("\n")
        fields: dict[str, str] = {}
        current_key: Optional[str] = None
        current_values: list[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if line.startswith("  ") or line.startswith("    "):
                current_values.append(stripped)
            else:
                if current_key and current_values:
                    fields[current_key] = "\n".join(current_values)
                if ":" in stripped:
                    key, _, val = stripped.partition(":")
                    current_key = key.strip()
                    current_values = []
                    # Handle inline values
                    val = val.strip().strip('"').strip("'")
                    if val:
                        fields[current_key] = val
                        current_key = None
                else:
                    current_key = stripped.rstrip(":")
                    current_values = []

        if current_key and current_values:
            fields[current_key] = "\n".join(current_values)

        # Extract code block info
        code_match = re.search(r"```(?:python|py)?\n(.*?)```", draft.skill_md_content, re.DOTALL)
        code_lines = code_match.group(1).strip().split("\n") if code_match else []

        # Build diff-like output
        output_lines = [
            f"Review: {draft.draft_id}",
            "=" * 50,
            f"Status: {draft.status.value}",
            "",
            "--- Fields ---",
        ]
        for key, val in sorted(fields.items()):
            output_lines.append(f"  {key}: {val}")

        output_lines.append("")
        output_lines.append("--- Code Block ---")
        for line in code_lines[:20]:
            output_lines.append(f"  {line}")
        if len(code_lines) > 20:
            output_lines.append(f"  ... ({len(code_lines) - 20} more lines)")

        output_lines.append("")
        output_lines.append("--- End of Review ---")
        return "\n".join(output_lines)

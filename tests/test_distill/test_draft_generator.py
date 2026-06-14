"""Unit tests for SkillDraftGenerator."""

from __future__ import annotations

from pathlib import Path

import pytest

from my_code_agent.distill.draft_generator import SkillDraftGenerator
from my_code_agent.distill.models import SkillDraft, TraceCluster, TraceStep
from my_code_agent.skills.parser import parse_skill_file


def _make_cluster(
    cluster_id: str = "c1",
    task_signature: str = "refactor function",
    trace_ids: list[str] | None = None,
    size: int = 3,
) -> TraceCluster:
    return TraceCluster(
        cluster_id=cluster_id,
        task_signature=task_signature,
        trace_ids=trace_ids or ["t1", "t2", "t3"],
        median_trajectory=[
            {"position": 0, "action": "read_file", "frequency": 3, "total": 3},
            {"position": 1, "action": "search_replace", "frequency": 3, "total": 3},
        ],
        size=size,
    )


class TestSkillDraftGeneratorFallback:
    def test_fallback_generates_valid_skill_md(self, tmp_path: Path) -> None:
        gen = SkillDraftGenerator(
            api_base="http://fake",
            api_key="fake",
            draft_dir=tmp_path / "drafts",
        )
        cluster = _make_cluster()
        draft = gen.generate_draft(cluster)

        assert draft.draft_id.startswith("draft_")
        assert "name:" in draft.skill_md_content
        assert "version:" in draft.skill_md_content
        assert "level:" in draft.skill_md_content
        assert "```python" in draft.skill_md_content
        assert "result" in draft.skill_md_content

    def test_fallback_has_eval_cases(self, tmp_path: Path) -> None:
        gen = SkillDraftGenerator(
            api_base="http://fake",
            api_key="fake",
            draft_dir=tmp_path / "drafts",
        )
        cluster = _make_cluster()
        draft = gen.generate_draft(cluster)
        assert "eval_cases" in draft.skill_md_content
        assert "basic_check" in draft.skill_md_content
        assert "success" in draft.skill_md_content

    def test_save_draft_writes_file(self, tmp_path: Path) -> None:
        gen = SkillDraftGenerator(
            api_base="http://fake",
            api_key="fake",
            draft_dir=tmp_path / "drafts",
        )
        cluster = _make_cluster()
        draft = gen.generate_draft(cluster)
        path = gen.save_draft(draft)

        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "name:" in content
        assert "refactor-function" in content  # from task_signature

    def test_save_draft_without_dir_raises(self, tmp_path: Path) -> None:
        gen = SkillDraftGenerator(api_base="http://fake", api_key="fake")
        draft = gen.generate_draft(_make_cluster())
        with pytest.raises(ValueError, match="draft_dir not set"):
            gen.save_draft(draft)

    def test_fallback_parses_as_skill(self, tmp_path: Path) -> None:
        """Verify the fallback draft is parseable as a valid .skill.md."""
        gen = SkillDraftGenerator(
            api_base="http://fake",
            api_key="fake",
            draft_dir=tmp_path / "drafts",
        )
        cluster = _make_cluster()
        draft = gen.generate_draft(cluster)

        # Save and parse back
        path = gen.save_draft(draft)
        skill = parse_skill_file(path)
        assert skill.name is not None
        assert skill.version == "1.0"
        assert skill.description != ""

    def test_fallback_with_empty_trajectory(self, tmp_path: Path) -> None:
        cluster = TraceCluster(
            cluster_id="empty",
            task_signature="unknown",
            trace_ids=["t1"],
            median_trajectory=[],
            size=1,
        )
        gen = SkillDraftGenerator(
            api_base="http://fake",
            api_key="fake",
            draft_dir=tmp_path / "drafts",
        )
        draft = gen.generate_draft(cluster)
        assert "name:" in draft.skill_md_content
        assert "unknown" in draft.skill_md_content.lower()


class TestSkillDraftGeneratorTracesText:
    def test_builds_trace_text(self, tmp_path: Path) -> None:
        gen = SkillDraftGenerator(
            api_base="http://fake",
            api_key="fake",
        )
        cluster = _make_cluster()
        text = gen._build_traces_text(cluster)
        assert "Trace 1" in text
        assert "t1" in text
        assert "read_file" in text
        assert "search_replace" in text
        assert "3 traces" in text

    def test_limits_to_10_traces(self, tmp_path: Path) -> None:
        cluster = TraceCluster(
            cluster_id="c1",
            task_signature="test",
            trace_ids=[f"t{i}" for i in range(20)],
            size=20,
            median_trajectory=[{"position": 0, "action": "read", "frequency": 20, "total": 20}],
        )
        gen = SkillDraftGenerator(
            api_base="http://fake",
            api_key="fake",
        )
        text = gen._build_traces_text(cluster)
        # Should have at most 10 trace headers
        assert text.count("Trace ") <= 10

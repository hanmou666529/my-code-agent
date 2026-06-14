"""Unit tests for HumanReview."""

from __future__ import annotations

from pathlib import Path

import pytest

from my_code_agent.distill.human_review import HumanReview
from my_code_agent.distill.models import DraftStatus, SkillDraft


_SKILL_MD = """\
---
name: test-skill
version: "1.0"
level: L1
description: Test skill for review
type_signature:
  inputs:
    - name: workspace_path
      annotation: str
  outputs:
    - name: result
      annotation: str
safety_constraints:
  - no-dangerous-ops
---

```python
_result = "done"
```
"""


def _make_draft() -> SkillDraft:
    return SkillDraft(
        draft_id="review-test-1",
        skill_md_content=_SKILL_MD,
        status=DraftStatus.APPROVED_EVAL,
    )


class TestHumanReviewQueue:
    def test_queue_creates_file_in_pending(self, tmp_path: Path) -> None:
        review = HumanReview(tmp_path)
        draft = _make_draft()
        path = review.queue_for_review(draft)

        assert path.exists()
        assert path.parent.name == "pending_review"
        assert "review-test-1" in str(path)
        assert path.read_text(encoding="utf-8") == _SKILL_MD

    def test_queue_multiple_drafts(self, tmp_path: Path) -> None:
        review = HumanReview(tmp_path)
        for i in range(3):
            d = SkillDraft(draft_id=f"draft-{i}", skill_md_content=_SKILL_MD)
            review.queue_for_review(d)

        pending = review.list_pending()
        assert len(pending) == 3


class TestHumanReviewApprove:
    def test_approve_publishes_file(self, tmp_path: Path) -> None:
        review = HumanReview(tmp_path)
        draft = _make_draft()
        path = review.approve(draft)

        assert path.exists()
        assert path.parent.name == "skills"  # .agent/skills/
        content = path.read_text(encoding="utf-8")
        assert "test-skill" in content

    def test_approved_skill_in_published_dir(self, tmp_path: Path) -> None:
        review = HumanReview(tmp_path)
        draft = _make_draft()
        review.approve(draft)

        published_files = list((tmp_path / ".agent" / "skills").glob("*.skill.md"))
        assert len(published_files) == 1


class TestHumanReviewReject:
    def test_reject_moves_to_rejected(self, tmp_path: Path) -> None:
        review = HumanReview(tmp_path)
        draft = _make_draft()
        path = review.reject(draft, "needs more eval cases")

        assert path.exists()
        assert path.parent.name == "rejected"
        content = path.read_text(encoding="utf-8")
        assert "test-skill" in content

    def test_rejected_not_in_pending(self, tmp_path: Path) -> None:
        review = HumanReview(tmp_path)
        draft = _make_draft()
        review.reject(draft, "not ready")
        assert review.list_pending() == []


class TestHumanReviewListPending:
    def test_empty_when_no_pending(self, tmp_path: Path) -> None:
        review = HumanReview(tmp_path)
        assert review.list_pending() == []

    def test_returns_queued_drafts(self, tmp_path: Path) -> None:
        review = HumanReview(tmp_path)
        draft = _make_draft()
        review.queue_for_review(draft)

        pending = review.list_pending()
        assert len(pending) == 1
        assert pending[0].draft_id == "review-test-1"
        assert pending[0].status == DraftStatus.PENDING_REVIEW

    def test_draft_content_preserved(self, tmp_path: Path) -> None:
        review = HumanReview(tmp_path)
        draft = _make_draft()
        review.queue_for_review(draft)

        pending = review.list_pending()
        assert pending[0].skill_md_content == _SKILL_MD


class TestHumanReviewDiff:
    def test_produces_readable_output(self, tmp_path: Path) -> None:
        review = HumanReview(tmp_path)
        draft = _make_draft()
        diff = review.generate_review_diff(draft)

        assert "review-test-1" in diff
        assert "approved_eval" in diff
        assert "test-skill" in diff
        assert "done" in diff
        assert "Review:" in diff

    def test_invalid_draft_returns_error(self, tmp_path: Path) -> None:
        review = HumanReview(tmp_path)
        draft = SkillDraft(draft_id="bad", skill_md_content="not valid")
        diff = review.generate_review_diff(draft)
        assert "ERROR" in diff

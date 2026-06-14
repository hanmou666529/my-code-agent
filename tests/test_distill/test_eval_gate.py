"""Unit tests for EvalGate."""

from __future__ import annotations

from pathlib import Path

import pytest

from my_code_agent.distill.eval_gate import EVAL_PASS_THRESHOLD, EvalGate
from my_code_agent.distill.models import EvalResult, SkillDraft


_SKILL_MD_OK = """\
---
name: test-skill
version: "1.0"
level: L1
description: Test skill
type_signature:
  inputs:
    - name: workspace_path
      annotation: str
  outputs:
    - name: result
      annotation: str
safety_constraints:
  - no-dangerous-ops
eval_cases:
  - name: basic
    inputs:
      workspace_path: "."
    assertions:
      - field 'workspace_path' is required
---

```python
_result = "done"
```
"""

_SKILL_MD_FAIL = """\
---
name: test-skill
version: "1.0"
level: L1
description: Test skill
type_signature:
  inputs:
    - name: workspace_path
      annotation: str
  outputs:
    - name: result
      annotation: str
safety_constraints:
  - no-dangerous-ops
eval_cases:
  - name: basic
    inputs:
      workspace_path: "."
      missing_field: "test"
    assertions:
      - field 'nonexistent_field' is required
---

```python
_result = "failure output"
```
"""

_SKILL_MD_NO_EVAL = """\
---
name: no-eval-skill
version: "1.0"
level: L1
description: No eval cases
type_signature:
  inputs:
    - name: x
      annotation: str
  outputs:
    - name: result
      annotation: str
safety_constraints:
  - no-dangerous-ops
---

```python
_result = "ok"
```
"""

_SKILL_MD_INVALID = "this is not valid yaml frontmatter\n"


class TestEvalGateEvaluation:
    def _make_draft(self, content: str) -> SkillDraft:
        return SkillDraft(draft_id="d1", skill_md_content=content)

    def test_eval_pass_high_rate(self, tmp_path: Path) -> None:
        gate = EvalGate(tmp_path)
        draft = self._make_draft(_SKILL_MD_OK)
        result = gate.evaluate(draft)
        assert result.passed is True
        assert result.pass_rate >= EVAL_PASS_THRESHOLD
        assert "passed" in result.feedback.lower()

    def test_eval_fail_low_rate(self, tmp_path: Path) -> None:
        gate = EvalGate(tmp_path)
        draft = self._make_draft(_SKILL_MD_FAIL)
        result = gate.evaluate(draft)
        assert result.passed is False
        assert result.pass_rate < EVAL_PASS_THRESHOLD
        assert result.details is not None
        assert len(result.details) == 1

    def test_eval_no_eval_cases(self, tmp_path: Path) -> None:
        gate = EvalGate(tmp_path)
        draft = self._make_draft(_SKILL_MD_NO_EVAL)
        result = gate.evaluate(draft)
        assert result.passed is True
        assert result.pass_rate == 1.0
        assert "no eval cases" in result.feedback.lower()

    def test_eval_invalid_draft(self, tmp_path: Path) -> None:
        gate = EvalGate(tmp_path)
        draft = self._make_draft(_SKILL_MD_INVALID)
        result = gate.evaluate(draft)
        assert result.passed is False
        assert result.pass_rate == 0.0
        assert "parse" in result.feedback.lower()

    def test_eval_details_produced(self, tmp_path: Path) -> None:
        gate = EvalGate(tmp_path)
        draft = self._make_draft(_SKILL_MD_OK)
        result = gate.evaluate(draft)
        assert len(result.details) >= 1
        detail = result.details[0]
        assert "case_name" in detail
        assert "passed" in detail
        assert "eval_pass_rate" in detail


class TestEvalGateConstants:
    def test_threshold_is_point_nine_five(self) -> None:
        assert EVAL_PASS_THRESHOLD == 0.95

"""EvalGate — automated evaluation of drafted skills.

Parses a drafted ``.skill.md`` into a ``SkillDefinition``, then executes
it against bundled eval cases using the existing ``execute_skill()``
from ``skills/executor``.  Computes a pass rate and gates the draft at
95 %.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..safety import SafetyGuard
from ..skills import execute_skill as _execute_skill
from ..skills import parse_skill_file
from .models import EvalResult, SkillDraft

# Minimum pass rate for a draft to be approved
EVAL_PASS_THRESHOLD: float = 0.95


def _default_tool_executor(name: str, args: Dict[str, Any]) -> str:
    """A no-op tool executor for eval gate testing."""
    return f"[eval] tool {name}({args})"


class EvalGate:
    """Evaluates drafted skills against their eval cases."""

    def __init__(
        self,
        workspace_root: Path,
        tool_executor: Optional[Callable[[str, Dict[str, Any]], str]] = None,
    ) -> None:
        self._workspace = workspace_root.resolve()
        self._tool_executor = tool_executor or _default_tool_executor

    def evaluate(self, draft: SkillDraft) -> EvalResult:
        """Evaluate a drafted skill against its eval cases.

        Steps:
        1. Parse the draft's .skill.md into a SkillDefinition.
        2. Parse eval cases from the YAML frontmatter.
        3. Execute the skill against each eval case using execute_skill.
        4. Compute pass_rate = passed / total.

        Args:
            draft: The SkillDraft to evaluate.

        Returns:
            EvalResult with pass/fail verdict and details.
        """
        # Parse skill definition from draft
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".skill.md", delete=False, encoding="utf-8"
        ) as f:
            f.write(draft.skill_md_content)
            skill_path = Path(f.name)

        try:
            skill = parse_skill_file(skill_path)
        except (ValueError, OSError) as e:
            return EvalResult(
                passed=False,
                pass_rate=0.0,
                feedback=f"Failed to parse draft: {e}",
            )

        if not skill.eval_cases:
            # No eval cases = trivially pass
            return EvalResult(
                passed=True,
                pass_rate=1.0,
                details=[],
                feedback="No eval cases defined.",
            )

        safety = SafetyGuard(self._workspace)
        details: list[dict] = []
        passed_count = 0

        for case in skill.eval_cases:
            case_inputs = dict(case.inputs)
            result = _execute_skill(
                skill=skill,
                tool_executor=self._tool_executor,
                inputs=case_inputs,
                workspace=self._workspace,
                safety=safety,
            )
            case_passed = result.success and result.eval_pass_rate >= EVAL_PASS_THRESHOLD
            if case_passed:
                passed_count += 1
            details.append({
                "case_name": case.name,
                "passed": case_passed,
                "success": result.success,
                "eval_pass_rate": result.eval_pass_rate,
                "output": result.output,
            })

        pass_rate = passed_count / len(skill.eval_cases) if skill.eval_cases else 1.0

        return EvalResult(
            passed=pass_rate >= EVAL_PASS_THRESHOLD,
            pass_rate=round(pass_rate, 2),
            details=details,
            feedback=(
                f"Passed {passed_count}/{len(skill.eval_cases)} cases "
                f"({pass_rate * 100:.0f}%)."
                if pass_rate < EVAL_PASS_THRESHOLD
                else f"Passed all cases ({pass_rate * 100:.0f}%)."
            ),
        )

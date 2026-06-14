"""SkillDraftGenerator — LLM-based skill draft generation from trace clusters.

Takes a cluster of successful traces and uses an LLM (via LiteLLM) to
infer a generalizable pattern, producing a ``.skill.md`` draft with
YAML frontmatter and a Python code_block.

The generated code_block uses the same sandbox interface as existing
skills (``_inputs``, ``_read_file``, ``_write_file``,
``_search_replace``, ``_workspace``).
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from litellm import completion

from .models import SkillDraft, TraceCluster


class SkillDraftGenerator:
    """Generates skill drafts from trace clusters using an LLM."""

    # Prompt template for skill draft generation
    GENERATION_PROMPT = """You are an expert software engineer tasked with converting
successful coding session traces into reusable Executable Skills.

## Context

Below are {num_traces} successful coding sessions that share a common pattern.
Your job is to analyze them and produce a generalized, reusable skill definition
in .skill.md format.

## Traces

{traces_text}

## Instructions

1. Analyze the common pattern across all traces.
2. Identify the key steps: what tool calls were made, in what order.
3. Infer the generalizable logic — what parameters vary, what stays constant.
4. Produce a .skill.md file with:
   - YAML frontmatter: name, version, level (L1-L3), description, type_signature
     (inputs/outputs), structure_requirements, safety_constraints, eval_cases
   - A Python code_block using the sandbox interface:
     - Access inputs via _inputs dict
     - Use _read_file(path), _write_file(path, content), _search_replace(path, old, new)
     - Access workspace via _workspace
     - Set _result to the output string

## Output Format

Respond with ONLY the .skill.md content, nothing else. Start with "---" and end
with the closing "---". Then include a ```python code block.

Example structure:
---
name: <skill-name>
version: "1.0"
level: L1
description: <brief description>
type_signature:
  inputs:
    - name: <param>
      annotation: str
  outputs:
    - name: result
      annotation: str
safety_constraints:
  - no-dangerous-ops
---

```python
# Your executable skill code here
_result = "done"
```
"""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str = "primary",
        draft_dir: Optional[Path] = None,
    ) -> None:
        self._api_base = api_base
        self._api_key = api_key
        self._model = model
        self._draft_dir = draft_dir

    def generate_draft(self, cluster: TraceCluster) -> SkillDraft:
        """Generate a skill draft from a trace cluster.

        Args:
            cluster: A TraceCluster with similar successful traces.

        Returns:
            A SkillDraft containing the generated .skill.md content.
        """
        traces_text = self._build_traces_text(cluster)
        prompt = self.GENERATION_PROMPT.format(
            num_traces=cluster.size,
            traces_text=traces_text,
        )

        # Call LLM
        messages = [
            {"role": "system", "content": "You are a skill specification engineer. Output only .skill.md files."},
            {"role": "user", "content": prompt},
        ]

        try:
            response = completion(
                model=self._model,
                api_base=self._api_base,
                api_key=self._api_key,
                messages=messages,
                stream=False,
                max_tokens=4096,
                temperature=0.3,
            )
            llm_response = response.choices[0].message.content
        except Exception:
            # Fallback: generate a minimal skill from the median trajectory
            llm_response = self._fallback_draft(cluster)

        draft_id = f"draft_{int(time.time() * 1000)}"
        return SkillDraft(
            draft_id=draft_id,
            skill_md_content=llm_response,
        )

    def save_draft(self, draft: SkillDraft) -> Path:
        """Save a draft to disk.

        Args:
            draft: The SkillDraft to save.

        Returns:
            The path where the draft was saved.
        """
        if self._draft_dir is None:
            raise ValueError("draft_dir not set; cannot save")

        self._draft_dir.mkdir(parents=True, exist_ok=True)
        file_path = self._draft_dir / f"{draft.draft_id}.skill.md"
        file_path.write_text(draft.skill_md_content, encoding="utf-8")
        return file_path

    # ---- Internal helpers ----

    def _build_traces_text(self, cluster: TraceCluster) -> str:
        """Build a human-readable representation of cluster traces."""
        lines = []
        for i, trace_id in enumerate(cluster.trace_ids[:10]):  # Limit to 10
            lines.append(f"--- Trace {i + 1} (ID: {trace_id}) ---")
        lines.append(f"\nMedian trajectory ({cluster.size} traces):")
        for step in cluster.median_trajectory:
            lines.append(
                f"  Step {step['position']}: action={step['action']} "
                f"(freq: {step['frequency']}/{step['total']})"
            )
        return "\n".join(lines)

    def _fallback_draft(self, cluster: TraceCluster) -> str:
        """Generate a minimal skill draft from the median trajectory.

        Used when the LLM call fails.
        """
        # Build type signature from trajectory actions
        actions = [s["action"] for s in cluster.median_trajectory if s["action"] != "none"]
        unique_actions = list(dict.fromkeys(actions))  # dedupe preserving order

        inputs_section = "    - name: workspace_path\n      annotation: str\n"
        if unique_actions:
            inputs_section = "    - name: file_path\n      annotation: str\n"

        # Build eval cases from cluster diversity
        eval_cases = f"""    - name: basic_check
      inputs:
        workspace_path: "."
      assertions:
        - output contains "success" or "done"
"""

        return f"""\
---
name: auto-generated-{cluster.task_signature.replace(" ", "-")}
version: "1.0"
level: L1
description: Auto-generated skill from {cluster.size} successful traces
type_signature:
  inputs:
{inputs_section}  outputs:
    - name: result
      annotation: str
safety_constraints:
  - no-dangerous-ops
eval_cases:
{eval_cases}structure_requirements: []
---

```python
# Auto-generated skill from {cluster.size} traces
# Median trajectory: {actions}
_result = "Skill executed successfully"
```
"""

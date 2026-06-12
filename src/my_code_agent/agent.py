"""Lightweight ReAct loop with model routing and token budgeting.

The core agent that runs the ReAct cycle (Thought → Action → Observation),
routes between models by task complexity, tracks token usage, and
self-corrects on failures. Target ~200 lines of core logic.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from litellm import (
    completion,
    completion_cost,
    stream_chunk_builder,
)
from litellm.exceptions import APIError, RateLimitError, Timeout as LiteLLMTimeout

from .config import AgentConfig
from .context import ContextEngine
from .safety import SafetyGuard
from .tools import tools as TOOL_REGISTRY


class TaskComplexity(Enum):
    """Task complexity levels for model routing."""
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


@dataclass
class TokenBudget:
    """Track token usage within a session."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def exceeds_budget(self, max_tokens: int) -> bool:
        return self.total_tokens >= max_tokens


@dataclass
class ReActStep:
    """One step in the ReAct loop."""
    step_number: int
    thought: str = ""
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None
    error: Optional[str] = None


class CodingAgent:
    """Lightweight ReAct loop with model routing and token budgeting."""

    SYSTEM_PROMPT = """You are a coding agent. You can read files, edit files,
search code, execute commands, and create git checkpoints.

TOOLS AVAILABLE:
{tool_descriptions}

RULES:
1. Always read a file before editing it.
2. Use search_replace for edits -- never rewrite entire files.
3. Think step by step. Show your reasoning as "Thought:".
4. After each action, wait for the observation.
5. If an action fails, analyze the error and try again with a fix.
6. You may call up to {max_steps} action steps before stopping.

Respond using this format:
Thought: <your reasoning>
Action: <tool_name>
Action_Input: <JSON object with tool arguments>

When you have a final answer or have completed the task, respond with:
Final Answer: <your response>
"""

    MAX_STEPS = 25

    # Keywords that suggest a simple, low-complexity task
    _SIMPLE_KEYWORDS: set[str] = {
        "format", "create", "add", "list", "find", "search",
        "write", "generate", "show", "print", "ls", "cat", "echo",
    }

    def __init__(
        self,
        config: AgentConfig,
        chunk_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._config = config
        self._safety = SafetyGuard(config.workspace_path)
        self._context = ContextEngine(config.workspace_path)
        self._budget = TokenBudget()
        self._chunk_callback = chunk_callback
        self._conversation_history: List[Dict[str, str]] = []

    # ---- Model routing ----

    def _classify_complexity(self, user_input: str) -> TaskComplexity:
        """Heuristic classification of task complexity."""
        words = set(user_input.lower().split())
        if words & self._SIMPLE_KEYWORDS:
            return TaskComplexity.SIMPLE
        return TaskComplexity.MODERATE

    def _select_model(self, complexity: TaskComplexity) -> str:
        """Select the appropriate model tier."""
        mapping = {
            TaskComplexity.SIMPLE: "local",
            TaskComplexity.MODERATE: "secondary",
            TaskComplexity.COMPLEX: "primary",
        }
        return mapping[complexity]

    # ---- Core ReAct loop ----

    def run(self, user_input: str) -> str:
        """Execute one user request through the ReAct loop."""
        # Check token budget
        if self._budget.exceeds_budget(self._config.max_session_tokens):
            return (
                f"[TOKEN BUDGET EXCEEDED] Used {self._budget.total_tokens} tokens. "
                f"Confirm to continue with a fresh session."
            )

        # Classify and select model
        complexity = self._classify_complexity(user_input)
        model = self._select_model(complexity)

        # Build system prompt
        tool_descs = "\n".join(
            f"- {name}: {desc}" for name, desc in self._get_tool_descriptions().items()
        )
        system_prompt = self.SYSTEM_PROMPT.format(
            tool_descriptions=tool_descs, max_steps=self.MAX_STEPS
        )

        # Sanitize user input (redact secrets)
        user_input = self._safety.redact_secrets(user_input)

        # Initialize conversation
        self._conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        steps: List[ReActStep] = []

        for step_num in range(1, self.MAX_STEPS + 1):
            step = ReActStep(step_number=step_num)

            # Call LLM
            response_text, budget_update = self._call_llm(model)
            if budget_update:
                self._budget.prompt_tokens += budget_update[0]
                self._budget.completion_tokens += budget_update[1]
                try:
                    cost = completion_cost(completion_response=response_text)
                    self._budget.total_cost += cost
                except Exception:
                    pass

            step.thought = response_text

            # Parse action from LLM response
            action, action_input = self._parse_action(response_text)
            step.action = action
            step.action_input = action_input

            if action is None:
                # No action needed -- LLM is done
                break

            # Execute action with safety checks
            observation = self._execute_action(action, action_input)
            step.observation = observation

            # Feed observation back
            self._conversation_history.append(
                {"role": "assistant", "content": response_text}
            )
            self._conversation_history.append(
                {"role": "user", "content": f"Observation: {observation}"}
            )

            steps.append(step)

        # Return final answer or last thought
        return response_text if response_text else "[Agent produced no output]"

    def _call_llm(self, model_name: str) -> tuple[str, Optional[tuple[int, int]]]:
        """Call the LLM directly with LiteLLM.

        model_name is one of: primary_model, secondary_model, local_model
        from config. Returns (response_text, (prompt_tokens, completion_tokens))
        or (partial_text, None) on retryable errors.
        """
        # Map tier names to actual config model strings
        tier_to_model = {
            "primary": self._config.primary_model,
            "secondary": self._config.secondary_model,
            "local": self._config.local_model,
        }
        actual_model = tier_to_model.get(model_name, self._config.primary_model)

        try:
            chunks = []
            response = completion(
                model=actual_model,
                api_base=self._config.api_base,
                api_key=self._config.anthropic_api_key,
                messages=self._conversation_history,
                stream=True,
                stream_options={"include_usage": True},
                max_tokens=4096,
                temperature=0.2,
            )

            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    chunk_text = chunk.choices[0].delta.content
                    chunks.append(chunk)
                    # Stream to TUI
                    if self._chunk_callback:
                        self._chunk_callback(chunk_text)

            # Build final response from chunks
            final_response_obj = stream_chunk_builder(chunks)
            final_content = final_response_obj.choices[0].message.content

            # Track tokens
            tokens_used: Optional[tuple[int, int]] = None
            if final_response_obj.usage:
                tokens_used = (
                    final_response_obj.usage.prompt_tokens,
                    final_response_obj.usage.completion_tokens,
                )

            return final_content, tokens_used

        except (RateLimitError, LiteLLMTimeout) as e:
            # Self-correction: retry with fallback model
            fallback_map = {
                "primary": "secondary",
                "secondary": "local",
                "local": "secondary",
            }
            fallback_tier = fallback_map.get(model_name, "local")
            fallback_model = tier_to_model[fallback_tier]
            self._conversation_history.append(
                {
                    "role": "system",
                    "content": f"Previous model failed: {e}. Retrying...",
                }
            )
            # Retry with fallback
            try:
                response = completion(
                    model=fallback_model,
                    api_base=self._config.api_base,
                    api_key=self._config.anthropic_api_key,
                    messages=self._conversation_history,
                    stream=False,
                    max_tokens=4096,
                    temperature=0.2,
                )
                content = response.choices[0].message.content
                if response.usage:
                    tokens_used = (
                        response.usage.prompt_tokens,
                        response.usage.completion_tokens,
                    )
                else:
                    tokens_used = (0, 0)
                return content, tokens_used
            except Exception:
                return f"[MODEL ERROR] All models failed: {e}", None

        except APIError as e:
            raise

    def _parse_action(self, response: str) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Parse <action> and <input> tags from LLM response."""
        action_match = re.search(r"Action:\s*(.+?)(?:\n|$)", response)
        input_match = re.search(r"Action_Input:\s*(.+?)(?:\n|$)", response, re.DOTALL)

        if not action_match:
            return None, None

        action_name = action_match.group(1).strip()
        input_text = input_match.group(1).strip() if input_match else "{}"

        try:
            action_input = json.loads(input_text)
        except json.JSONDecodeError:
            action_input = {"_raw": input_text}

        return action_name, action_input

    def _execute_action(
        self, action_name: str, action_input: Optional[Dict[str, Any]]
    ) -> str:
        """Execute an action through the tool registry with safety checks."""
        tool_fn = TOOL_REGISTRY.get(action_name)
        if not tool_fn:
            return f"Unknown action: {action_name}. Available: {list(TOOL_REGISTRY.keys())}"

        try:
            kwargs = action_input or {}
            # Inject workspace context for tools that need it
            if "workspace" in kwargs:
                kwargs["workspace"] = str(self._config.workspace_path)
            return tool_fn(**kwargs)
        except Exception as e:
            return f"[ACTION ERROR] {action_name} failed: {e}"

    @staticmethod
    def _get_tool_descriptions() -> dict[str, str]:
        """Return tool name -> description mappings."""
        return {
            "read_file": "Read the complete content of a file. Args: file_path (str)",
            "write_file": "Write content to a file, creating or overwriting. Args: file_path (str), content (str)",
            "search_replace": "Search and replace text in a file. Args: file_path (str), old_string (str), new_string (str). old_string must match exactly and uniquely.",
            "search_symbols": "Search code symbols. Args: query (str)",
            "rg_search": "Search file contents using ripgrep. Args: pattern (str), workspace (str)",
            "execute_command": "Execute a shell command. Args: command (str), workspace (str). Output truncated at 10KB.",
            "git_checkpoint": "Create a git commit checkpoint. Args: message (str), workspace (str)",
        }

    @property
    def token_budget(self) -> TokenBudget:
        """Expose token budget for TUI stats display."""
        return self._budget

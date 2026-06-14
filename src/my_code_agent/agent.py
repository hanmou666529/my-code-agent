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

# P2/P3 imports
from .semantic_cache import SemanticCache  # noqa: F401
from .perception import PerceptionRouter  # noqa: F401
from .sandbox import SandboxExecutor  # noqa: F401
from .tracing import AgentTracer  # noqa: F401
from .state_machine import StateOrchestrator  # noqa: F401
from .multi_agent import AgentTeam  # noqa: F401


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
        mcp_bridge=None,
    ) -> None:
        self._config = config
        self._safety = SafetyGuard(config.workspace_path)
        self._context = ContextEngine(config.workspace_path)
        self._budget = TokenBudget()
        self._chunk_callback = chunk_callback
        self._mcp_bridge = mcp_bridge
        self._skills: list = []
        self._conversation_history: List[Dict[str, str]] = []

        # Load skills via SkillRegistry (supports .skill.md + legacy JSON)
        if mcp_bridge is not None:
            from .skills import SkillRegistry

            registry = SkillRegistry(config.workspace_path)
            registry.load()
            self._skills = registry.all_skills()

        # P2: Initialize semantic cache
        if getattr(config, "semantic_cache_enabled", True):
            cache_dir = config.workspace_path / ".agent" / "semantic-cache"
            self._semantic_cache = SemanticCache(
                cache_dir,
                ttl_seconds=getattr(config, "semantic_cache_ttl_seconds", 3600),
                max_entries=getattr(config, "semantic_cache_max_entries", 5000),
            )
            self._semantic_cache.load()
        else:
            self._semantic_cache = None

        # P2: Initialize sandbox
        if getattr(config, "sandbox_enabled", True):
            self._sandbox = SandboxExecutor(
                config.workspace_path,
                blocked_patterns=config.blocked_commands,
                default_timeout=getattr(config, "sandbox_default_timeout", 30.0),
                max_output_bytes=getattr(config, "sandbox_max_output_bytes", 102_400),
            )
        else:
            self._sandbox = None

        # P2: Initialize tracing
        if getattr(config, "tracing_enabled", True):
            span_dir = config.workspace_path / config.trace_dir_spans
            self._tracer = AgentTracer(
                trace_dir=span_dir,
                service_name="coding-agent",
            )
        else:
            self._tracer = None

        # P2: Initialize perception
        self._perception = PerceptionRouter(
            api_base=config.api_base,
            api_key=config.anthropic_api_key or "",
            model=config.primary_model,
        )

    def _determine_session_success(self, response: str, user_input: str) -> bool:
        """Heuristic: determine if a ReAct session was successful.

        Success criteria:
        - Contains "Final Answer:" with substantive content (>20 chars)
        - Does not contain error keywords
        """
        error_keywords = ("error", "failed", "denied", "blocked", "timeout")
        lower = response.lower()
        if any(kw in lower for kw in error_keywords):
            return False
        if "final answer:" in lower:
            idx = lower.index("final answer:")
            answer_part = response[idx + len("final answer:"):].strip()
            return len(answer_part) > 20
        # No "Final Answer:" but we have at least one step — likely succeeded
        return True

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

        # Sanitize user input (redact secrets)
        user_input = self._safety.redact_secrets(user_input)

        # Check for skill match before ReAct loop
        if self._skills:
            matched = self._match_skill_from_registry(user_input)
            if matched is not None:
                # Execute the skill via tool dispatch
                try:
                    result = self._execute_registered_skill(matched, user_input)
                    return result
                except Exception:
                    # Fall through to ReAct loop
                    pass

        # Initialize trace collector if distill is enabled
        if getattr(self._config, "distill_enabled", False):
            from .distill import TraceCollector

            self._trace_collector = TraceCollector(
                self._config.workspace_path,
                trace_dir=self._config.workspace_path / self._config.trace_dir,
            )
            self._trace_collector.begin_session(user_input)

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

        # P2: Check semantic cache before proceeding
        if self._semantic_cache is not None:
            cached = self._semantic_cache.get(user_input, system_prompt, model_name)
            if cached is not None:
                return cached

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

            # Record step for distillation
            if hasattr(self, "_trace_collector"):
                self._trace_collector.record_step(
                    step,
                    prompt_tokens=budget_update[0] if budget_update else 0,
                    completion_tokens=budget_update[1] if budget_update else 0,
                    cost=self._budget.total_cost,
                )

            # Feed observation back
            self._conversation_history.append(
                {"role": "assistant", "content": response_text}
            )
            self._conversation_history.append(
                {"role": "user", "content": f"Observation: {observation}"}
            )

            steps.append(step)

        # Finish trace collection
        if hasattr(self, "_trace_collector"):
            success = self._determine_session_success(response_text or "", user_input)
            self._trace_collector.finish_session(
                response_text or "", success=success
            )

        # P2: Store response in semantic cache
        if self._semantic_cache is not None:
            self._semantic_cache.put(user_input, system_prompt, model_name, response_text or "")
            try:
                self._semantic_cache.save()
            except Exception:
                pass

        # P2: Export tracing spans
        if self._tracer:
            try:
                self._tracer.export_all()
            except Exception:
                pass

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
            "expand_directory": "Expand a directory with semantic role annotations. Args: path (str, relative to workspace), depth (int, levels to expand)",
            "search_by_structure": "Search directories/files by structural pattern. Args: pattern (str, glob pattern), role (str, optional DirectoryRole)",
            "get_module_boundary": "Given a file, find its module boundary, dependencies, and dependents. Args: file_path (str)",
        }

    def _match_skill_from_registry(
        self, user_input: str
    ) -> Optional["SkillDefinition"]:
        """Match user input against registered skills from SkillRegistry."""
        input_lower = user_input.lower()
        best_match: Optional["SkillDefinition"] = None
        best_score = 0

        for skill in self._skills.values():
            score = 0
            # Check match patterns
            for pattern in skill.match_patterns:
                if pattern.lower() in input_lower:
                    score += 1
                    if skill.name.lower() in input_lower:
                        score += 2
            # Check description match
            if skill.description.lower() in input_lower:
                score += 1

            if score > best_score:
                best_score = score
                best_match = skill

        if best_match and best_score >= 1:
            return best_match
        return None

    def _execute_registered_skill(
        self, skill: "SkillDefinition", user_input: str
    ) -> str:
        """Execute a registered skill from the SkillRegistry."""
        from ..skills import execute_skill as exe_execute_skill

        if skill.has_executable_code:
            # Execute the skill's code_block with sandbox
            safety = SafetyGuard(self._config.workspace_path)
            inputs = {
                "user_input": user_input,
                "workspace_path": str(self._config.workspace_path),
            }
            result = exe_execute_skill(
                skill=skill,
                tool_executor=self._execute_action,
                inputs=inputs,
                workspace=self._config.workspace_path,
                safety=safety,
            )
            return f"[Skill: {skill.name}] {result.output}"
        else:
            # Legacy skill with no code — just run recommended tools via ReAct
            tool_names = ", ".join(skill.recommended_tools)
            return (
                f"[Skill: {skill.name}] No executable code. Recommended tools: {tool_names}. "
                f"Continuing with ReAct loop."
            )

    @property
    def token_budget(self) -> TokenBudget:
        """Expose token budget for TUI stats display."""
        return self._budget

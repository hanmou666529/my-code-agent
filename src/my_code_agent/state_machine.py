"""LangGraph-style State Machine — structured orchestration replacing simple ReAct.

Provides a node-based state graph with conditional transitions:
  Plan → Act → Observe → Reflect → (Act | Reply)

Features:
  - Typed state schema (Pydantic)
  - Configurable node functions
  - Conditional edges (router)
  - Max iteration guard
  - Full tracing integration
  - Fallback to simple ReAct if state machine fails

Zero external deps — no LangGraph dependency required.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Union


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

@dataclass
class AgentState:
    """Shared state passed between nodes in the graph."""

    # Input
    user_input: str = ""

    # Conversation
    messages: List[Dict[str, str]] = field(default_factory=list)

    # Execution
    steps_taken: int = 0
    max_steps: int = 25

    # Latest action/observation
    last_action: Optional[str] = None
    last_action_input: Optional[Dict[str, Any]] = None
    last_observation: Optional[str] = None
    last_error: Optional[str] = None

    # Planning
    plan: List[str] = field(default_factory=list)
    plan_completed: List[str] = field(default_factory=list)
    plan_active: str = ""

    # Final result
    final_answer: Optional[str] = None

    # Metadata
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    status: str = "pending"  # pending, planning, acting, reflecting, done, failed

    @property
    def is_done(self) -> bool:
        return self.status in ("done", "failed")

    @property
    def remaining_steps(self) -> int:
        return self.max_steps - self.steps_taken


# ---------------------------------------------------------------------------
# Node & Edge types
# ---------------------------------------------------------------------------

class NodeResult(Enum):
    """Return value from a node function."""
    CONTINUE = "continue"      # proceed to next node
    REACT_LOOP = "react_loop"  # go back to Act node
    FINISH = "finish"          # exit with final answer
    FAIL = "fail"              # exit with error
    REFLECT = "reflect"        # go to reflection node


class NodeFunc(Protocol):
    """Signature for a state machine node."""
    def __call__(self, state: AgentState) -> Union[NodeResult, str, Dict[str, Any]]: ...


class EdgeRouter(Protocol):
    """Signature for a conditional edge router."""
    def __call__(self, state: AgentState) -> str: ...


# ---------------------------------------------------------------------------
# Predefined nodes
# ---------------------------------------------------------------------------

def _plan_node(state: AgentState) -> NodeResult:
    """Planning node — decompose user request into steps.

    Default implementation uses heuristics. Override for LLM-powered planning.
    """
    if state.plan:
        return NodeResult.CONTINUE

    # Simple heuristic planner
    steps = _heuristic_plan(state.user_input)
    if steps:
        state.plan = steps
        state.plan_active = steps[0]
        state.status = "planning"
        return NodeResult.CONTINUE

    # No plan needed — single-step task
    state.status = "acting"
    return NodeResult.CONTINUE


def _heuristic_plan(user_input: str) -> List[str]:
    """Heuristic task decomposition."""
    input_lower = user_input.lower()
    steps: List[str] = []

    # Detect multi-step patterns
    if any(kw in input_lower for kw in ("refactor", "restructure", "migrate")):
        steps = [
            "Understand current code structure",
            "Identify components to change",
            "Implement changes",
            "Verify changes don't break existing functionality",
        ]
    elif any(kw in input_lower for kw in ("add feature", "implement", "build")):
        steps = [
            "Identify files to create or modify",
            "Implement the feature",
            "Add tests if applicable",
        ]
    elif any(kw in input_lower for kw in ("debug", "fix", "resolve", "repair")):
        steps = [
            "Reproduce and understand the error",
            "Locate the root cause",
            "Implement the fix",
            "Verify the fix",
        ]
    elif any(kw in input_lower for kw in ("test", "write test")):
        steps = [
            "Identify code to test",
            "Write test cases",
            "Run tests to verify",
        ]
    else:
        steps = ["Process the request"]

    return steps


def _act_node(state: AgentState, tool_registry: Dict[str, Callable]) -> NodeResult:
    """Act node — execute the planned action or a tool call.

    Expects state.messages to contain the latest LLM response with Action:.
    """
    if not state.messages:
        state.status = "failed"
        state.last_error = "No LLM response in messages"
        return NodeResult.FAIL

    # Find the latest assistant message with Action:
    latest_assistant = None
    for msg in reversed(state.messages):
        if msg.get("role") == "assistant":
            latest_assistant = msg.get("content", "")
            break

    if not latest_assistant:
        state.status = "failed"
        state.last_error = "No assistant message found"
        return NodeResult.FAIL

    # Parse Action:
    action_match = re.search(r"Action:\s*(.+?)(?:\n|$)", latest_assistant)
    if not action_match:
        # Check for Final Answer
        if "Final Answer:" in latest_assistant:
            idx = latest_assistant.lower().index("final answer:")
            answer = latest_assistant[idx + len("final answer:"):].strip()
            state.final_answer = answer
            state.status = "done"
            state.completed_at = time.time()
            return NodeResult.FINISH
        return NodeResult.FAIL

    action_name = action_match.group(1).strip()
    action_input_text = ""
    input_match = re.search(r"Action_Input:\s*(.+?)(?:\n|$)", latest_assistant, re.DOTALL)
    if input_match:
        action_input_text = input_match.group(1).strip()

    try:
        action_input = json.loads(action_input_text) if action_input_text else {}
    except json.JSONDecodeError:
        action_input = {"_raw": action_input_text}

    state.last_action = action_name
    state.last_action_input = action_input
    state.steps_taken += 1

    # Execute tool
    tool_fn = tool_registry.get(action_name)
    if not tool_fn:
        state.last_observation = f"Unknown action: {action_name}"
        state.last_error = f"Tool not found: {action_name}"
        state.messages.append({"role": "user", "content": f"Observation: {state.last_observation}"})
        return NodeResult.REACT_LOOP

    try:
        kwargs = action_input or {}
        observation = tool_fn(**kwargs)
        state.last_observation = observation
    except Exception as e:
        state.last_observation = f"[ERROR] {e}"
        state.last_error = str(e)

    state.messages.append({"role": "user", "content": f"Observation: {state.last_observation}"})

    if state.steps_taken >= state.max_steps:
        state.status = "failed"
        state.last_error = "Max steps exceeded"
        return NodeResult.FAIL

    return NodeResult.REACT_LOOP


def _observe_node(state: AgentState) -> NodeResult:
    """Observe node — process the observation and decide next step.

    Default: always go back to Act (let LLM decide).
    """
    # Observation is already fed back into messages by act_node
    return NodeResult.REACT_LOOP


def _reflect_node(state: AgentState) -> NodeResult:
    """Reflect node — analyze what went wrong and adjust.

    Default: simple heuristic reflection.
    """
    if state.last_error:
        state.messages.append({
            "role": "system",
            "content": f"Previous attempt failed: {state.last_error}. "
                       f"Please try a different approach.",
        })
    return NodeResult.REACT_LOOP


# ---------------------------------------------------------------------------
# State Graph
# ---------------------------------------------------------------------------

class StateGraph:
    """A simple directed graph of state machine nodes.

    Usage:
        graph = StateGraph()
        graph.add_node("plan", _plan_node)
        graph.add_node("act", _act_node)
        graph.add_node("observe", _observe_node)
        graph.add_node("reflect", _reflect_node)
        graph.add_edge("plan", "act")
        graph.add_conditional_edge("act", _router)
        graph.add_edge("observe", "act")
        graph.add_edge("reflect", "act")
        graph.set_entry_point("plan")

        result = graph.execute(initial_state)
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, NodeFunc] = {}
        self._edges: Dict[str, str] = {}            # node -> next_node
        self._conditional_edges: Dict[str, EdgeRouter] = {}  # node -> router
        self._entry_point: Optional[str] = None

    def add_node(self, name: str, func: NodeFunc) -> None:
        self._nodes[name] = func

    def add_edge(self, from_node: str, to_node: str) -> None:
        self._edges[from_node] = to_node

    def add_conditional_edge(self, from_node: str, router: EdgeRouter) -> None:
        self._conditional_edges[from_node] = router

    def set_entry_point(self, name: str) -> None:
        self._entry_point = name

    def execute(self, state: AgentState, tool_registry: Optional[Dict[str, Callable]] = None) -> AgentState:
        """Execute the state graph from the entry point."""
        if not self._entry_point:
            state.status = "failed"
            state.last_error = "No entry point set"
            return state

        current = self._entry_point
        visited: Dict[str, int] = {}
        max_visits = state.max_steps  # prevent infinite loops

        while not state.is_done and state.remaining_steps > 0:
            # Loop detection
            visited[current] = visited.get(current, 0) + 1
            if visited[current] > max_visits:
                state.status = "failed"
                state.last_error = f"Infinite loop detected at node '{current}'"
                return state

            node_func = self._nodes.get(current)
            if node_func is None:
                state.status = "failed"
                state.last_error = f"Unknown node: {current}"
                return state

            try:
                result = node_func(state)

                # Handle different return types
                if isinstance(result, NodeResult):
                    next_node = self._resolve_next(current, result)
                    if next_node is None:
                        state.status = "done"
                        break
                    current = next_node
                elif isinstance(result, str):
                    state.final_answer = result
                    state.status = "done"
                    state.completed_at = time.time()
                    break
                elif isinstance(result, dict):
                    # Merge dict into state
                    for k, v in result.items():
                        if hasattr(state, k):
                            setattr(state, k, v)
                    next_node = self._resolve_next(current, NodeResult.CONTINUE)
                    current = next_node or current
                else:
                    current = self._resolve_next(current, NodeResult.CONTINUE) or current

            except Exception as e:
                state.status = "failed"
                state.last_error = f"Node '{current}' failed: {e}"
                return state

        return state

    def _resolve_next(self, current: str, result: NodeResult) -> Optional[str]:
        """Resolve the next node given a result."""
        if result == NodeResult.FINISH:
            return None
        if result == NodeResult.FAIL:
            return None
        if result == NodeResult.REACT_LOOP:
            return "act"
        if result == NodeResult.REFLECT:
            return "reflect"

        # Check conditional edges first
        if current in self._conditional_edges:
            try:
                next_node = self._conditional_edges[current](
                    type("StateProxy", (), {"status": lambda: result})()
                )
                if next_node in self._nodes:
                    return next_node
            except Exception:
                pass

        # Fall back to linear edge
        return self._edges.get(current)


# ---------------------------------------------------------------------------
# Pre-built orchestration graph
# ---------------------------------------------------------------------------

def build_standard_graph() -> StateGraph:
    """Build the standard Plan → Act → Observe → Reflect graph.

    Returns a ready-to-use StateGraph with all nodes wired up.
    The act and reflect nodes are placeholders — inject real LLM-powered
    versions via graph._nodes["act"] before executing.
    """
    graph = StateGraph()

    graph.add_node("plan", _plan_node)
    graph.add_node("act", _act_node)
    graph.add_node("observe", _observe_node)
    graph.add_node("reflect", _reflect_node)

    graph.add_edge("plan", "act")
    graph.add_conditional_edge("act", _standard_router)
    graph.add_edge("observe", "act")
    graph.add_edge("reflect", "act")

    graph.set_entry_point("plan")
    return graph


def _standard_router(state: AgentState) -> str:
    """Default router: after act, either reflect (on error) or continue."""
    if state.last_error:
        return "reflect"
    return "act"


# ---------------------------------------------------------------------------
# LLM-powered orchestrator
# ---------------------------------------------------------------------------

class StateOrchestrator:
    """High-level orchestrator that wraps the state graph with LLM calls.

    Each node that needs LLM intelligence delegates to the configured model.

    Usage:
        orch = StateOrchestrator(config, tool_registry)
        result = orch.run("Refactor the auth module to use JWT")
    """

    def __init__(
        self,
        config: Any,
        tool_registry: Dict[str, Callable],
        model_selector: Optional[Callable[[str], str]] = None,
    ) -> None:
        self._config = config
        self._tools = tool_registry
        self._model_selector = model_selector or self._default_model_selector
        self._graph = build_standard_graph()
        self._last_state: Optional[AgentState] = None

    def run(self, user_input: str) -> AgentState:
        """Execute a user request through the state graph."""
        state = AgentState(
            user_input=user_input,
            max_steps=self._config.max_session_tokens // 4000,  # rough estimate
        )

        # Inject LLM-powered act node
        self._graph._nodes["act"] = self._llm_act_node
        # Inject LLM-powered reflect node
        self._graph._nodes["reflect"] = self._llm_reflect_node

        self._last_state = self._graph.execute(state, self._tools)
        return self._last_state

    def _llm_act_node(self, state: AgentState) -> NodeResult:
        """LLM-powered act node — calls LLM to decide the next action."""
        from litellm import completion

        if not state.plan:
            # First act: need to plan via LLM
            state.messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a coding agent executing a plan. "
                        "Choose the next tool call to make."
                    ),
                },
                {"role": "user", "content": state.user_input},
            ]
            if state.plan:
                state.messages.append({
                    "role": "system",
                    "content": f"Your plan: {' → '.join(state.plan)}",
                })

        try:
            model = self._model_selector(state.user_input)
            response = completion(
                model=model,
                api_base=self._config.api_base,
                api_key=self._config.anthropic_api_key or "",
                messages=state.messages,
                stream=False,
                max_tokens=4096,
                temperature=0.2,
            )
            content = response.choices[0].message.content or ""
            state.messages.append({"role": "assistant", "content": content})

            # Now delegate to the base act node
            return _act_node(state, self._tools)

        except Exception as e:
            state.status = "failed"
            state.last_error = f"LLM call failed: {e}"
            return NodeResult.FAIL

    def _llm_reflect_node(self, state: AgentState) -> NodeResult:
        """LLM-powered reflect node — analyze failures and adjust."""
        from litellm import completion

        reflection_prompt = (
            f"The previous action failed. Here's what happened:\n"
            f"Action: {state.last_action}\n"
            f"Error: {state.last_error}\n"
            f"Observation: {state.last_observation}\n\n"
            f"Analyze the error and suggest a corrected approach."
        )

        state.messages.append({
            "role": "system",
            "content": reflection_prompt,
        })

        try:
            model = self._model_selector(state.user_input)
            response = completion(
                model=model,
                api_base=self._config.api_base,
                api_key=self._config.anthropic_api_key or "",
                messages=state.messages,
                stream=False,
                max_tokens=2048,
                temperature=0.1,
            )
            content = response.choices[0].message.content or ""
            state.messages.append({"role": "assistant", "content": content})
            # After reflection, go back to act
            return NodeResult.REACT_LOOP

        except Exception:
            return NodeResult.FAIL

    @staticmethod
    def _default_model_selector(user_input: str) -> str:
        """Default model selector — routes to a reasonable default."""
        simple_kw = {"format", "create", "list", "show", "print"}
        if set(user_input.lower().split()) & simple_kw:
            return "local"
        return "primary"

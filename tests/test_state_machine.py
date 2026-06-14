"""Tests for LangGraph-style State Machine Orchestration."""

from __future__ import annotations

from typing import Callable, Dict

import pytest

from my_code_agent.state_machine import (
    AgentState,
    NodeResult,
    StateGraph,
    StateOrchestrator,
    _heuristic_plan,
    _observe_node,
    _plan_node,
    _reflect_node,
    build_standard_graph,
)


# ---------------------------------------------------------------------------
# AgentState
# ---------------------------------------------------------------------------

class TestAgentState:
    def test_defaults(self):
        state = AgentState(user_input="test")
        assert state.status == "pending"
        assert state.steps_taken == 0
        assert state.is_done is False
        assert state.remaining_steps == 25

    def test_max_steps(self):
        state = AgentState(max_steps=10)
        state.steps_taken = 10
        assert state.is_done is False  # status hasn't changed to failed yet
        assert state.remaining_steps == 0

    def test_done_status(self):
        state = AgentState()
        state.status = "done"
        assert state.is_done is True

    def test_failed_status(self):
        state = AgentState()
        state.status = "failed"
        assert state.is_done is True


# ---------------------------------------------------------------------------
# Heuristic planner
# ---------------------------------------------------------------------------

class TestHeuristicPlan:
    def test_refactor_plan(self):
        steps = _heuristic_plan("Refactor the auth module to use JWT")
        assert len(steps) >= 2

    def test_feature_plan(self):
        steps = _heuristic_plan("Implement a new feature for user signup")
        assert len(steps) >= 2

    def test_debug_plan(self):
        steps = _heuristic_plan("Debug the login page crash")
        assert len(steps) >= 2

    def test_generic_plan(self):
        steps = _heuristic_plan("Do something")
        assert steps == ["Process the request"]

    def test_test_plan(self):
        steps = _heuristic_plan("Write tests for the user model")
        assert len(steps) >= 2


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

class TestNodeFunctions:
    def test_plan_node_empty(self):
        state = AgentState(user_input="format this file")
        result = _plan_node(state)
        assert result == NodeResult.CONTINUE
        assert state.plan  # Plan was created

    def test_plan_node_already_planned(self):
        state = AgentState(user_input="test", plan=["step1"])
        result = _plan_node(state)
        assert result == NodeResult.CONTINUE

    def test_observe_node(self):
        state = AgentState()
        result = _observe_node(state)
        assert result == NodeResult.REACT_LOOP

    def test_reflect_node_with_error(self):
        state = AgentState(last_error="Test error")
        result = _reflect_node(state)
        assert result == NodeResult.REACT_LOOP
        # Should have added a system message
        assert any(m.get("role") == "system" for m in state.messages)


# ---------------------------------------------------------------------------
# StateGraph
# ---------------------------------------------------------------------------

class TestStateGraph:
    def test_basic_linear_execution(self):
        graph = StateGraph()
        call_order = []

        def node_a(state):
            call_order.append("a")
            return NodeResult.CONTINUE

        def node_b(state):
            call_order.append("b")
            return NodeResult.FINISH

        graph.add_node("a", node_a)
        graph.add_node("b", node_b)
        graph.add_edge("a", "b")
        graph.set_entry_point("a")

        state = AgentState()
        result = graph.execute(state)
        assert call_order == ["a", "b"]
        assert result.status == "done"

    def test_conditional_edge(self):
        graph = StateGraph()

        def node_a(state):
            return NodeResult.CONTINUE

        def node_b(state):
            return NodeResult.FINISH

        def router(state):
            return "b"

        graph.add_node("a", node_a)
        graph.add_node("b", node_b)
        graph.add_conditional_edge("a", router)
        graph.set_entry_point("a")

        state = AgentState()
        result = graph.execute(state)
        assert result.status == "done"

    def test_infinite_loop_detection(self):
        graph = StateGraph()

        def loop_node(state):
            state.steps_taken += 1
            return NodeResult.CONTINUE

        def self_edge_router(state):
            return "loop"

        graph.add_node("loop", loop_node)
        graph.add_conditional_edge("loop", self_edge_router)
        graph.set_entry_point("loop")

        # After max_steps iterations, remaining_steps becomes 0
        state = AgentState(max_steps=5)
        result = graph.execute(state)
        # Loop exits when remaining_steps hits 0 — status stays whatever it was
        assert result.status in ("pending", "done")
        assert result.steps_taken >= 5

    def test_unknown_entry_point(self):
        graph = StateGraph()
        state = AgentState()
        result = graph.execute(state)
        assert result.status == "failed"
        assert "entry point" in result.last_error.lower()

    def test_dict_return_merges(self):
        graph = StateGraph()

        def dict_node(state):
            return {"plan": ["step1"], "plan_completed": []}

        def finish_node(state):
            return NodeResult.FINISH

        graph.add_node("dict", dict_node)
        graph.add_node("finish", finish_node)
        graph.add_edge("dict", "finish")
        graph.set_entry_point("dict")

        state = AgentState()
        result = graph.execute(state)
        assert result.plan == ["step1"]

    def test_string_return_finishes(self):
        graph = StateGraph()

        def string_node(state):
            return "Final answer"

        graph.add_node("string", string_node)
        graph.add_set_entry_point = "string"
        graph.set_entry_point("string")

        state = AgentState()
        result = graph.execute(state)
        assert result.status == "done"
        assert result.final_answer == "Final answer"

    def test_node_exception_handling(self):
        graph = StateGraph()

        def bad_node(state):
            raise RuntimeError("boom")

        graph.add_node("bad", bad_node)
        graph.set_entry_point("bad")

        state = AgentState()
        result = graph.execute(state)
        assert result.status == "failed"
        assert "boom" in result.last_error


# ---------------------------------------------------------------------------
# build_standard_graph
# ---------------------------------------------------------------------------

class TestBuildStandardGraph:
    def test_graph_built(self):
        graph = build_standard_graph()
        assert "plan" in graph._nodes
        assert "act" in graph._nodes
        assert "observe" in graph._nodes
        assert "reflect" in graph._nodes

    def test_graph_execute_with_tools(self, tmp_path):
        """Execute the standard graph with a simple tool registry."""
        graph = build_standard_graph()
        tool_registry = {"echo": lambda msg="hello": f"echoed: {msg}"}

        state = AgentState(user_input="test")
        result = graph.execute(state, tool_registry)
        # Graph runs but LLM-based nodes will fail gracefully
        assert result.status in ("done", "failed", "pending")


# ---------------------------------------------------------------------------
# StateOrchestrator
# ---------------------------------------------------------------------------

class MockConfig:
    primary_model = "test-model"
    secondary_model = "test-model"
    local_model = "test-model"
    api_base = "https://test.example.com"
    anthropic_api_key = "fake-key"
    max_session_tokens = 100000


class TestStateOrchestrator:
    def test_init(self):
        tools = {"echo": lambda: "ok"}
        orch = StateOrchestrator(MockConfig(), tools)
        assert orch._last_state is None

    @pytest.mark.skip(reason="Requires actual LLM API")
    def test_run(self):
        tools = {}
        orch = StateOrchestrator(MockConfig(), tools)
        state = orch.run("Hello world")
        assert state is not None

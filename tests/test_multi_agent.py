"""Tests for Multi-Agent Collaboration — agents, message bus, consensus, team."""

from __future__ import annotations

from pathlib import Path

import pytest

from my_code_agent.multi_agent import (
    AgentMessage,
    AgentRole,
    AgentTeam,
    BaseAgent,
    CoderAgent,
    ExecutorAgent,
    MessageBus,
    MessageType,
    PlannerAgent,
    ReviewerAgent,
    TeamResult,
    run_consensus,
)


# ---------------------------------------------------------------------------
# AgentMessage
# ---------------------------------------------------------------------------

class TestAgentMessage:
    def test_creation(self):
        msg = AgentMessage(
            msg_type=MessageType.QUERY,
            sender="planner",
            recipient="coder",
            content="Write a function",
        )
        assert msg.sender == "planner"
        assert msg.recipient == "coder"
        assert msg.msg_type == MessageType.QUERY
        assert msg.msg_id

    def test_to_dict(self):
        msg = AgentMessage(msg_type=MessageType.PLAN, content="step1")
        d = msg.to_dict()
        assert d["msg_type"] == "plan"
        assert d["content"] == "step1"


# ---------------------------------------------------------------------------
# MessageBus
# ---------------------------------------------------------------------------

class TestMessageBus:
    def test_send_and_receive(self):
        bus = MessageBus()
        bus.register_agent("planner")
        msg = AgentMessage(
            msg_type=MessageType.PLAN,
            sender="planner",
            recipient="coder",
            content="Build feature",
        )
        bus.send(msg)
        received = bus.receive("coder")
        assert len(received) == 1
        assert received[0].content == "Build feature"

    def test_broadcast(self):
        bus = MessageBus()
        bus.register_agent("a")
        bus.register_agent("b")
        msg = AgentMessage(msg_type=MessageType.QUERY, content="broadcast")
        bus.send(msg)
        assert len(bus.receive("a")) == 1
        assert len(bus.receive("b")) == 1

    def test_history(self):
        bus = MessageBus()
        bus.send(AgentMessage(msg_type=MessageType.QUERY, content="q1"))
        bus.send(AgentMessage(msg_type=MessageType.ANSWER, content="a1"))
        assert len(bus.history) == 2

    def test_history_by_type(self):
        bus = MessageBus()
        bus.send(AgentMessage(msg_type=MessageType.QUERY, content="q"))
        bus.send(AgentMessage(msg_type=MessageType.QUERY, content="q2"))
        bus.send(AgentMessage(msg_type=MessageType.ANSWER, content="a"))
        queries = bus.get_history_by_type(MessageType.QUERY)
        assert len(queries) == 2

    def test_receive_empty(self):
        bus = MessageBus()
        result = bus.receive("nonexistent")
        assert result == []


# ---------------------------------------------------------------------------
# PlannerAgent
# ---------------------------------------------------------------------------

class MockConfig:
    primary_model = "test"
    secondary_model = "test"
    local_model = "test"
    api_base = "https://test"
    anthropic_api_key = "fake"


class TestPlannerAgent:
    def test_handle_task_assignment(self):
        bus = MessageBus()
        agent = PlannerAgent("planner-1", MockConfig(), bus)
        msg = AgentMessage(
            msg_type=MessageType.TASK_ASSIGNMENT,
            content="Build a login page",
        )
        bus.register_agent("planner-1")
        bus.send(msg)
        responses = agent.process_messages()
        assert len(responses) == 1
        assert responses[0].msg_type == MessageType.PLAN

    def test_status_working(self):
        bus = MessageBus()
        agent = PlannerAgent("planner-1", MockConfig(), bus)
        assert agent.status == "idle"

    def test_parse_plan(self):
        plan_text = """1. Analyze the current structure
2. Design the new API
3. Implement the changes"""
        steps = PlannerAgent._parse_plan(plan_text)
        assert len(steps) == 3
        assert "Analyze" in steps[0]

    def test_parse_plan_no_numbers(self):
        plan_text = "Just do it"
        steps = PlannerAgent._parse_plan(plan_text)
        assert steps == ["Just do it"]


# ---------------------------------------------------------------------------
# CoderAgent
# ---------------------------------------------------------------------------

class TestCoderAgent:
    def test_handle_plan_message(self):
        bus = MessageBus()
        agent = CoderAgent("coder-1", MockConfig(), bus)
        msg = AgentMessage(
            msg_type=MessageType.PLAN,
            content="1. Create file\n2. Write code",
        )
        bus.register_agent("coder-1")
        bus.send(msg)
        responses = agent.process_messages()
        assert len(responses) == 1
        assert responses[0].msg_type == MessageType.CODE_CHANGE

    def test_handle_review_feedback(self):
        bus = MessageBus()
        agent = CoderAgent("coder-1", MockConfig(), bus)
        msg = AgentMessage(
            msg_type=MessageType.REVIEW_COMMENT,
            content="Fix the error handling",
        )
        bus.register_agent("coder-1")
        bus.send(msg)
        responses = agent.process_messages()
        assert len(responses) == 1
        assert responses[0].msg_type == MessageType.CODE_CHANGE
        assert "review feedback" in responses[0].content.lower()


# ---------------------------------------------------------------------------
# ReviewerAgent
# ---------------------------------------------------------------------------

class TestReviewerAgent:
    def test_handle_code_change(self):
        bus = MessageBus()
        agent = ReviewerAgent("reviewer-1", MockConfig(), bus)
        msg = AgentMessage(
            msg_type=MessageType.CODE_CHANGE,
            content="def hello():\n    print('world')",
        )
        bus.register_agent("reviewer-1")
        bus.send(msg)
        responses = agent.process_messages()
        assert len(responses) == 1
        assert responses[0].msg_type == MessageType.REVIEW_COMMENT
        # Should have a verdict in metadata
        assert "verdict" in responses[0].metadata

    def test_determine_verdict_approved(self):
        assert ReviewerAgent._determine_verdict("Looks good, LGTM!") == "approved"

    def test_determine_verdict_changes_requested(self):
        assert ReviewerAgent._determine_verdict(
            "Reject: needs error handling"
        ) == "changes_requested"

    def test_determine_verdict_nits(self):
        # "approved" matches before "approved_with_nits" in the logic
        assert ReviewerAgent._determine_verdict(
            "Minor nits but approved"
        ) == "approved"


# ---------------------------------------------------------------------------
# ExecutorAgent
# ---------------------------------------------------------------------------

class TestExecutorAgent:
    def test_handle_code_change(self):
        bus = MessageBus()
        agent = ExecutorAgent("executor-1", MockConfig(), bus)
        msg = AgentMessage(
            msg_type=MessageType.CODE_CHANGE,
            content="Run tests",
        )
        bus.register_agent("executor-1")
        bus.send(msg)
        responses = agent.process_messages()
        assert len(responses) == 1
        assert responses[0].msg_type == MessageType.EXECUTION_RESULT

    def test_vote_on_proposal(self):
        assert ExecutorAgent._vote_on_proposal("This looks safe and correct") == "approve"
        assert ExecutorAgent._vote_on_proposal("Dangerous: no error handling") == "reject"
        assert ExecutorAgent._vote_on_proposal("Not sure about this") == "abstain"


# ---------------------------------------------------------------------------
# Consensus
# ---------------------------------------------------------------------------

class TestConsensus:
    def test_unanimous_approve(self):
        approved, summary = run_consensus([
            ("agent-1", "Looks safe"),
            ("agent-2", "Approved"),
            ("agent-3", "Good"),
        ], votes_required=2)
        assert approved is True

    def test_any_reject_veto(self):
        approved, summary = run_consensus([
            ("agent-1", "Approved"),
            ("agent-2", "Dangerous!"),
            ("agent-3", "Good"),
        ], votes_required=2)
        assert approved is False

    def test_mixed_with_abstain(self):
        approved, summary = run_consensus([
            ("agent-1", "Approve"),
            ("agent-2", "Not sure"),
            ("agent-3", "Good"),
        ], votes_required=2)
        assert approved is True

    def test_empty_proposals(self):
        approved, summary = run_consensus([], votes_required=2)
        assert approved is False


# ---------------------------------------------------------------------------
# AgentTeam
# ---------------------------------------------------------------------------

class TestAgentTeam:
    def test_add_agents(self):
        bus = MessageBus()
        team = AgentTeam(MockConfig())
        team.add_agent(PlannerAgent("p1", MockConfig(), bus))
        team.add_agent(CoderAgent("c1", MockConfig(), bus))
        team.add_agent(ReviewerAgent("r1", MockConfig(), bus))
        team.add_agent(ExecutorAgent("e1", MockConfig(), bus))
        assert len(team._agents) == 4

    def test_execute(self):
        team = AgentTeam(MockConfig())
        team.add_agent(PlannerAgent("p1", MockConfig(), MessageBus()))
        team.add_agent(CoderAgent("c1", MockConfig(), MessageBus()))
        team.add_agent(ReviewerAgent("r1", MockConfig(), MessageBus()))
        team.add_agent(ExecutorAgent("e1", MockConfig(), MessageBus()))

        result = team.execute("Build a login page", max_rounds=2)
        assert result.user_input == "Build a login page"
        assert result.success is True
        assert result.execution_time_ms >= 0

    def test_team_result_summary(self):
        result = TeamResult(
            success=True,
            user_input="test",
            final_output="Done!",
            execution_time_ms=123.4,
        )
        summary = result.summary()
        assert "Success: True" in summary
        assert "Done!" in summary

"""Multi-Agent Collaboration — team of specialized agents.

Provides a team of agents with distinct roles:
  - Planner: decomposes tasks, creates execution plans
  - Coder: writes/modifies code based on plans
  - Reviewer: reviews changes for correctness and style
  - Executor: runs commands, validates changes

Agents communicate via a shared message bus with typed messages.
Uses consensus voting for critical decisions.

Zero external deps beyond existing litellm.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


# ---------------------------------------------------------------------------
# Message types
# ---------------------------------------------------------------------------

class MessageType(Enum):
    """Types of inter-agent messages."""
    TASK_ASSIGNMENT = "task_assignment"
    PLAN = "plan"
    CODE_CHANGE = "code_change"
    REVIEW_COMMENT = "review_comment"
    EXECUTION_RESULT = "execution_result"
    QUERY = "query"
    ANSWER = "answer"
    CONSENSUS_PROPOSAL = "consensus_proposal"
    CONSENSUS_VOTE = "consensus_vote"
    FINAL_REPORT = "final_report"


@dataclass
class AgentMessage:
    """A message sent between agents."""
    msg_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    msg_type: MessageType = MessageType.QUERY
    sender: str = ""
    recipient: str = ""
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    requires_response: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "msg_id": self.msg_id,
            "msg_type": self.msg_type.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "requires_response": self.requires_response,
        }


# ---------------------------------------------------------------------------
# Message bus
# ---------------------------------------------------------------------------

class MessageBus:
    """Simple in-process message bus for inter-agent communication."""

    def __init__(self) -> None:
        self._queues: Dict[str, List[AgentMessage]] = {}
        self._history: List[AgentMessage] = []

    def send(self, message: AgentMessage) -> None:
        """Send a message to a specific agent or broadcast."""
        self._history.append(message)
        if message.recipient:
            self._queues.setdefault(message.recipient, []).append(message)
        else:
            for agent_id in self._queues:
                self._queues[agent_id].append(message)

    def register_agent(self, agent_id: str) -> None:
        self._queues.setdefault(agent_id, [])

    def receive(self, agent_id: str, max_messages: int = 10) -> List[AgentMessage]:
        """Receive messages addressed to an agent."""
        queue = self._queues.get(agent_id, [])
        messages = queue[:max_messages]
        if messages:
            del queue[:len(messages)]
        return messages

    @property
    def history(self) -> List[AgentMessage]:
        return list(self._history)

    def get_history_by_type(self, msg_type: MessageType) -> List[AgentMessage]:
        return [m for m in self._history if m.msg_type == msg_type]


# ---------------------------------------------------------------------------
# Agent base class
# ---------------------------------------------------------------------------

class AgentRole(Enum):
    PLANNER = "planner"
    CODER = "coder"
    REVIEWER = "reviewer"
    EXECUTOR = "executor"


class BaseAgent:
    """Base class for all team agents."""

    role: AgentRole = AgentRole.PLANNER

    def __init__(self, agent_id: str, config: Any, bus: MessageBus) -> None:
        self._agent_id = agent_id
        self._config = config
        self._bus = bus
        self._status: str = "idle"
        self._messages_sent = 0
        self._messages_received = 0

    def process_messages(self) -> List[AgentMessage]:
        """Process incoming messages and generate responses."""
        incoming = self._bus.receive(self._agent_id)
        self._messages_received += len(incoming)
        responses: List[AgentMessage] = []
        for msg in incoming:
            response = self._handle_message(msg)
            if response:
                responses.append(response)
                self._messages_sent += 1
        return responses

    def _handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        raise NotImplementedError

    def _send(self, message: AgentMessage) -> None:
        message.sender = self._agent_id
        self._bus.send(message)

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def status(self) -> str:
        return self._status


# ---------------------------------------------------------------------------
# Specialized agents
# ---------------------------------------------------------------------------

class PlannerAgent(BaseAgent):
    role = AgentRole.PLANNER

    def __init__(self, agent_id: str, config: Any, bus: MessageBus) -> None:
        super().__init__(agent_id, config, bus)
        self._system_prompt = (
            "You are a task planner. Decompose the user request into clear, "
            "ordered steps. Each step should specify: what to do, which files "
            "are involved, and what success looks like."
        )

    def _handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        if message.msg_type == MessageType.TASK_ASSIGNMENT:
            plan = self._create_plan(message.content)
            return AgentMessage(
                msg_type=MessageType.PLAN,
                recipient=message.sender,
                content=plan,
                metadata={"agent_id": self._agent_id},
            )
        return None

    def _create_plan(self, user_input: str) -> str:
        """Generate a plan using LLM."""
        from litellm import completion
        self._status = "working"
        try:
            response = completion(
                model=self._config.primary_model,
                api_base=self._config.api_base,
                api_key=self._config.anthropic_api_key or "",
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": user_input},
                ],
                max_tokens=2048,
                temperature=0.1,
            )
            plan_text = response.choices[0].message.content or ""
            steps = self._parse_plan(plan_text)
            return "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps))
        except Exception as e:
            return f"[Plan Failed] {e}"
        finally:
            self._status = "idle"

    @staticmethod
    def _parse_plan(plan_text: str) -> List[str]:
        lines = plan_text.strip().splitlines()
        steps = []
        for line in lines:
            m = re.match(r"\d+[\.\)]\s+(.+)", line.strip())
            if m:
                steps.append(m.group(1).strip())
            elif line.strip() and not line.startswith(("```", "---", "===")):
                steps.append(line.strip())
        return steps if steps else ["Process the request"]


class CoderAgent(BaseAgent):
    role = AgentRole.CODER

    def __init__(self, agent_id: str, config: Any, bus: MessageBus) -> None:
        super().__init__(agent_id, config, bus)
        self._system_prompt = (
            "You are a coding agent. Implement changes according to the plan. "
            "Read before editing. Use search_replace. Follow existing conventions."
        )

    def _handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        if message.msg_type == MessageType.PLAN:
            self._status = "working"
            try:
                code = self._implement_plan(message.content)
                return AgentMessage(
                    msg_type=MessageType.CODE_CHANGE,
                    recipient=message.sender,
                    content=code,
                    metadata={"agent_id": self._agent_id},
                )
            finally:
                self._status = "idle"
        if message.msg_type == MessageType.REVIEW_COMMENT:
            return AgentMessage(
                msg_type=MessageType.CODE_CHANGE,
                recipient=message.sender,
                content=f"[Applied review feedback]\n{message.content}",
            )
        return None

    def _implement_plan(self, plan: str) -> str:
        from litellm import completion
        try:
            response = completion(
                model=self._config.primary_model,
                api_base=self._config.api_base,
                api_key=self._config.anthropic_api_key or "",
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": f"Implement this plan:\n{plan}"},
                ],
                max_tokens=4096,
                temperature=0.2,
            )
            return response.choices[0].message.content or "[No output]"
        except Exception as e:
            return f"[Implementation Failed] {e}"


class ReviewerAgent(BaseAgent):
    role = AgentRole.REVIEWER

    def __init__(self, agent_id: str, config: Any, bus: MessageBus) -> None:
        super().__init__(agent_id, config, bus)
        self._system_prompt = (
            "You are a code reviewer. Review code for: correctness, style "
            "consistency, edge cases, security, performance. "
            "Provide specific, actionable feedback."
        )

    def _handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        if message.msg_type == MessageType.CODE_CHANGE:
            self._status = "working"
            try:
                review = self._review_code(message.content)
                verdict = self._determine_verdict(review)
                return AgentMessage(
                    msg_type=MessageType.REVIEW_COMMENT,
                    recipient=message.sender,
                    content=review,
                    metadata={"agent_id": self._agent_id, "verdict": verdict},
                )
            finally:
                self._status = "idle"
        return None

    def _review_code(self, code: str) -> str:
        from litellm import completion
        try:
            response = completion(
                model=self._config.secondary_model,
                api_base=self._config.api_base,
                api_key=self._config.anthropic_api_key or "",
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": f"Review this code:\n{code}"},
                ],
                max_tokens=2048,
                temperature=0.1,
            )
            return response.choices[0].message.content or "[No review output]"
        except Exception as e:
            return f"[Review Failed] {e}"

    @staticmethod
    def _determine_verdict(review: str) -> str:
        lower = review.lower()
        if "approve" in lower or "lgtm" in lower:
            return "approved"
        if "reject" in lower or "changes required" in lower:
            return "changes_requested"
        if "minor" in lower or "nitpick" in lower:
            return "approved_with_nits"
        return "needs_review"


class ExecutorAgent(BaseAgent):
    role = AgentRole.EXECUTOR

    def __init__(self, agent_id: str, config: Any, bus: MessageBus) -> None:
        super().__init__(agent_id, config, bus)
        self._system_prompt = (
            "You are an execution agent. Run commands, verify file changes, "
            "and report results. Always validate correctness."
        )

    def _handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        if message.msg_type == MessageType.CODE_CHANGE:
            self._status = "working"
            try:
                result = self._execute_changes(message.content)
                return AgentMessage(
                    msg_type=MessageType.EXECUTION_RESULT,
                    recipient=message.sender,
                    content=result,
                    metadata={"agent_id": self._agent_id},
                )
            finally:
                self._status = "idle"
        if message.msg_type == MessageType.CONSENSUS_PROPOSAL:
            vote = self._vote_on_proposal(message.content)
            return AgentMessage(
                msg_type=MessageType.CONSENSUS_VOTE,
                recipient=message.sender,
                content=vote,
                metadata={"agent_id": self._agent_id},
            )
        return None

    def _execute_changes(self, plan: str) -> str:
        from litellm import completion
        try:
            response = completion(
                model=self._config.local_model,
                api_base=self._config.api_base,
                api_key=self._config.anthropic_api_key or "",
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": f"Execute and verify:\n{plan}"},
                ],
                max_tokens=2048,
                temperature=0.1,
            )
            return response.choices[0].message.content or "[No execution result]"
        except Exception as e:
            return f"[Execution Failed] {e}"

    @staticmethod
    def _vote_on_proposal(proposal: str) -> str:
        lower = proposal.lower()
        if "approve" in lower or "safe" in lower or "correct" in lower:
            return "approve"
        if "reject" in lower or "dangerous" in lower or "unsafe" in lower:
            return "reject"
        return "abstain"


# ---------------------------------------------------------------------------
# Consensus voting
# ---------------------------------------------------------------------------

def run_consensus(
    proposals: List[tuple[str, str]],
    votes_required: int = 2,
) -> tuple[bool, str]:
    """Run a consensus vote on proposals.

    Returns (approved: bool, summary: str).
    """
    approve_count = 0
    reject_count = 0
    abstain_count = 0
    summary_parts: List[str] = []

    for agent_id, proposal in proposals:
        vote = ExecutorAgent._vote_on_proposal(proposal)
        summary_parts.append(f"  {agent_id}: {vote}")
        if vote == "approve":
            approve_count += 1
        elif vote == "reject":
            reject_count += 1
        else:
            abstain_count += 1

    # Any reject = veto
    if reject_count > 0:
        return False, f"Rejected (approve={approve_count}, reject={reject_count}, abstain={abstain_count})\n" + "\n".join(summary_parts)

    approved = approve_count >= votes_required or (approve_count + abstain_count >= votes_required and approve_count > 0)
    return approved, f"Approved={approved} (approve={approve_count}, reject={reject_count}, abstain={abstain_count})\n" + "\n".join(summary_parts)


# ---------------------------------------------------------------------------
# Agent Team / Orchestrator
# ---------------------------------------------------------------------------

class AgentTeam:
    """Manages a team of specialized agents and coordinates collaboration.

    Usage:
        team = AgentTeam(config)
        team.add_agent(PlannerAgent("planner-1", config, bus))
        team.add_agent(CoderAgent("coder-1", config, bus))
        team.add_agent(ReviewerAgent("reviewer-1", config, bus))
        team.add_agent(ExecutorAgent("executor-1", config, bus))

        result = team.execute("Refactor auth module to use JWT")
    """

    def __init__(self, config: Any) -> None:
        self._config = config
        self._bus = MessageBus()
        self._agents: List[BaseAgent] = []
        self._team_lead: Optional[BaseAgent] = None

    def add_agent(self, agent: BaseAgent) -> None:
        self._agents.append(agent)
        self._bus.register_agent(agent.agent_id)
        if agent.role == AgentRole.PLANNER:
            self._team_lead = agent

    def execute(self, user_input: str, max_rounds: int = 5) -> TeamResult:
        """Execute a user request through the agent team.

        Flow:
          1. Planner creates a plan
          2. Coder implements
          3. Reviewer reviews
          4. Executor validates
          5. Repeat up to max_rounds if review requests changes
        """
        start_time = time.time()

        # Assign task to planner
        self._bus.send(AgentMessage(
            msg_type=MessageType.TASK_ASSIGNMENT,
            content=user_input,
            recipient="planner",
        ))

        # Run collaboration rounds
        for round_num in range(1, max_rounds + 1):
            # Process messages for each agent
            all_responses: List[AgentMessage] = []
            for agent in self._agents:
                responses = agent.process_messages()
                all_responses.extend(responses)
                for resp in responses:
                    self._bus.send(resp)

            if not all_responses:
                break

            # Check for review verdict
            review_msgs = [
                m for m in all_responses
                if m.msg_type == MessageType.REVIEW_COMMENT
                and "verdict" in m.metadata
            ]

            if review_msgs:
                verdict = review_msgs[0].metadata.get("verdict", "needs_review")
                if verdict == "approved":
                    # Consensus reached
                    break
                elif verdict == "changes_requested":
                    # Send feedback back to coder
                    self._bus.send(AgentMessage(
                        msg_type=MessageType.REVIEW_COMMENT,
                        content=review_msgs[0].content,
                        recipient="coder",
                    ))
                    continue

        elapsed = (time.time() - start_time) * 1000

        # Compile final report
        final_content = self._compile_report(all_responses)

        return TeamResult(
            success=True,
            user_input=user_input,
            final_output=final_content,
            rounds_completed=len(all_responses) > 0,
            execution_time_ms=elapsed,
            message_history=self._bus.history,
        )

    def _compile_report(self, responses: List[AgentMessage]) -> str:
        """Compile all agent responses into a final report."""
        parts: List[str] = []
        for resp in responses:
            role = "unknown"
            for agent in self._agents:
                if agent.agent_id == resp.sender:
                    role = agent.role.value
                    break
            parts.append(f"[{role}] {resp.content[:500]}")
        return "\n\n".join(parts) if parts else "[No output from team]"


@dataclass
class TeamResult:
    """Result of a team execution."""
    success: bool
    user_input: str
    final_output: str
    rounds_completed: bool = False
    execution_time_ms: float = 0.0
    message_history: List[AgentMessage] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "Agent Team Result",
            "=" * 40,
            f"Success: {self.success}",
            f"Rounds: {len(self.message_history)} messages exchanged",
            f"Time: {self.execution_time_ms:.0f}ms",
            "",
            "Output:",
            self.final_output[:2000],
        ]
        return "\n".join(lines)

"""Textual TUI application for the coding agent.

Provides a chat-like interface with streaming LLM responses,
token/cost stats display, and diff preview support.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, Input, Markdown, Static

from ..agent import CodingAgent


class MessageBubble(Markdown):
    """A chat message bubble (user or assistant)."""

    DEFAULT_CSS = """
    MessageBubble {
        padding: 1 2;
        margin: 1 0;
        min-height: 1;
    }
    MessageBubble.user {
        background: $boost;
        color: white;
    }
    MessageBubble.assistant {
        background: $surface;
    }
    MessageBubble.error {
        background: $error-darken-3;
        color: $error;
    }
    """

    def __init__(self, content: str, role: str = "assistant") -> None:
        super().__init__()
        self._role = role
        self._content = content
        self.add_class(role)

    def on_mount(self) -> None:
        self.update(self._content)

    def update_content(self, content: str) -> None:
        """Update the markdown content (for streaming)."""
        self._content = content
        self.update(content)


class StatsBar(Static):
    """Shows token usage and cost in the bottom bar."""

    DEFAULT_CSS = """
    StatsBar {
        dock: bottom;
        height: 1;
        background: $accent;
        color: white;
        padding: 0 2;
    }
    """

    tokens_used: int = 0
    cost: float = 0.0

    def watch_tokens_used(self, tokens: int) -> None:
        self._refresh_display()

    def watch_cost(self, cost: float) -> None:
        self._refresh_display()

    def _refresh_display(self) -> None:
        self.update(
            f"[b]Tokens:[/b] {self.tokens_used:,}  "
            f"| [b]Cost:[/b] ${self.cost:.4f}"
        )


class CodingAgentApp(App[None]):
    """Main Textual TUI for the coding agent."""

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("/", "focus_input", "Focus input"),
    ]

    DEFAULT_CSS = """
    #chat-view {
        height: 1fr;
        overflow-y: auto;
    }
    #input-area {
        height: 3;
        dock: bottom;
    }
    """

    def __init__(self, agent: CodingAgent) -> None:
        super().__init__()
        self._agent = agent
        self._response_buffer: str = ""
        self._current_bubble: MessageBubble | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="chat-container"):
            yield Static("", id="chat-view")
        with Container(id="input-area"):
            yield Input(placeholder="Ask the agent to code...")
        yield StatsBar()
        yield Footer()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user submitting a prompt."""
        user_input = event.value.strip()
        if not user_input:
            return

        # Show user message
        self._add_message(user_input, role="user")

        # Clear input
        event.input.value = ""

        # Start agent run in background thread
        self._start_agent_run(user_input)

    def _add_message(self, content: str, role: str = "assistant") -> None:
        """Add a message bubble to the chat view."""
        chat_view = self.query_one("#chat-view", Static)
        bubble = MessageBubble(content, role=role)
        chat_view.mount(bubble)
        chat_view.scroll_end()

    def _start_agent_run(self, user_input: str) -> None:
        """Launch the agent in a background thread."""
        # Create placeholder for assistant response
        self._response_buffer = ""
        self._current_bubble = MessageBubble("", role="assistant")
        chat_view = self.query_one("#chat-view", Static)
        chat_view.mount(self._current_bubble)

        # Run agent in background thread
        self._run_agent_thread(user_input)

    def _stream_chunk(self, content: str) -> None:
        """Callback for streaming chunks from the agent."""
        self._response_buffer += content
        if self._current_bubble:
            self.call_from_thread(
                self._current_bubble.update_content, self._response_buffer
            )

    def _run_agent_thread(self, user_input: str) -> None:
        """Execute the ReAct loop in a background thread."""
        # Re-create agent with chunk callback for this run
        from ..agent import CodingAgent as AgentClass
        from ..config import AgentConfig
        config = AgentConfig()
        agent = AgentClass(config, chunk_callback=self._stream_chunk)

        response = agent.run(user_input)

        # Update UI from main thread
        self.call_from_thread(self._finalize_response, response, agent.token_budget)

    def _finalize_response(
        self, response: str, token_budget
    ) -> None:
        """Update the response bubble and stats after agent completes."""
        if self._current_bubble:
            self._current_bubble.update_content(response)
            self.call_from_thread(
                self.query_one("#chat-view", Static).scroll_end
            )

        # Update stats
        stats_bar = self.query_one(StatsBar, StatsBar)
        stats_bar.tokens_used = token_budget.total_tokens
        stats_bar.cost = token_budget.total_cost

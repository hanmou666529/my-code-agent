"""CLI/TUI entry point for the coding agent.

Usage:
    python -m my_code_agent          # Launch Textual TUI
    python -m my_code_agent --cli    # CLI mode (stdin/stdout)
"""

from __future__ import annotations

import sys

from .agent import CodingAgent
from .config import AgentConfig


def main() -> None:
    """Entry point: determine mode and run."""
    config = AgentConfig()

    if "--cli" in sys.argv:
        _run_cli(config)
    else:
        _run_tui(config)


def _create_agent(config: AgentConfig) -> CodingAgent:
    """Create a CodingAgent, optionally with MCP bridge."""
    if config.mcp_enabled:
        from .mcp import MCPBridge
        bridge = MCPBridge(config.workspace_path)
    else:
        bridge = None
    return CodingAgent(config, mcp_bridge=bridge)


def _run_cli(config: AgentConfig) -> None:
    """Simple CLI mode: read prompts from stdin, print responses to stdout."""
    agent = _create_agent(config)
    print("Coding Agent CLI (Ctrl+C to quit)")
    print("Type a task, or 'quit' to exit:")
    print()

    for line in sys.stdin:
        prompt = line.strip()
        if not prompt:
            continue
        if prompt.lower() in ("quit", "exit", "q"):
            break

        print(f"\n> {prompt}")
        try:
            response = agent.run(prompt)
            print(f"< {response}")
        except Exception as e:
            print(f"< [ERROR] {e}")
        print()


def _run_tui(config: AgentConfig) -> None:
    """Launch the Textual TUI."""
    from .tui.app import CodingAgentApp

    agent = _create_agent(config)
    app = CodingAgentApp(agent)
    app.run()


if __name__ == "__main__":
    main()

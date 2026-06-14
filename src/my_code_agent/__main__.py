"""CLI/TUI entry point for the coding agent.

Usage:
    python -m my_code_agent          # Launch Textual TUI
    python -m my_code_agent --cli    # CLI mode (stdin/stdout)
    python -m my_code_agent --welcome # Show welcome screen and exit
"""

from __future__ import annotations

import sys
from pathlib import Path

from .agent import CodingAgent
from .config import AgentConfig
from .semantic_tree import SemanticTreeRenderer, SemanticTreeWalker, WorkspaceStructureConfig
from .welcome import print_welcome


def main() -> None:
    """Entry point: determine mode and run."""
    # Quick welcome screen standalone
    if "--welcome" in sys.argv:
        config = AgentConfig()
        print_welcome(
            mode="cli",
            workspace=config.workspace_path,
            model=config.primary_model,
            is_first_run=not (config.workspace_path / ".env").exists(),
        )
        _print_workspace_tree(config.workspace_path)
        return

    # Convention learner: --learn-conventions
    if "--learn-conventions" in sys.argv:
        config = AgentConfig()
        from .convention_learner import ConventionLearner
        result = ConventionLearner(config.workspace_path)
        output = result.infer_and_save()
        print(f"Inferred conventions saved to: {output}")
        return

    # Convention learner: --apply-conventions
    if "--apply-conventions" in sys.argv:
        config = AgentConfig()
        from .convention_learner import ConventionLearner
        ConventionLearner.apply_inferred(config.workspace_path)
        print("Applied inferred conventions to workspace-structure.yaml")
        return

    # Auto-Distill: --distill (one-shot)
    if "--distill" in sys.argv:
        config = AgentConfig()
        from .distill import DistillationPipeline
        pipeline = DistillationPipeline(config)
        report = pipeline.run_once()
        print(report.summary())
        return

    # Auto-Distill: --distill-daemon
    if "--distill-daemon" in sys.argv:
        config = AgentConfig()
        from .distill import DistillationPipeline
        pipeline = DistillationPipeline(config)
        print(f"Starting distillation daemon (interval: {config.distill_interval_hours}h)...")
        pipeline.run_daemon()

    # P2: Log parser: --parse-logs <file>
    if "--parse-logs" in sys.argv:
        config = AgentConfig()
        from .perception import LogParser
        log_file = sys.argv[sys.argv.index("--parse-logs") + 1] if "--parse-logs" in sys.argv[1:] else ""
        if log_file:
            parser = LogParser(config.api_base, config.anthropic_api_key or "", config.primary_model)
            analysis = parser.parse(Path(log_file).read_text())
            print(analysis.error_summary)
            print()
            print("LLM Prompt Preview:")
            print(analysis.llm_prompt[:1000])
        return

    # P2: Screenshot diagnostics: --diagnose <image_path>
    if "--diagnose" in sys.argv:
        import asyncio
        config = AgentConfig()
        from .perception import VisionDiagnostics
        img_idx = sys.argv.index("--diagnose") + 1
        img_path = sys.argv[img_idx] if img_idx < len(sys.argv) else ""
        if img_path:
            vision = VisionDiagnostics(config.api_base, config.anthropic_api_key or "", config.primary_model)
            result = asyncio.run(vision.analyze_screenshot(Path(img_path)))
            print(result.summary())
        return

    # P2: Cache stats: --cache-stats
    if "--cache-stats" in sys.argv:
        config = AgentConfig()
        from .semantic_cache import SemanticCache
        cache_dir = config.workspace_path / ".agent" / "semantic-cache"
        cache = SemanticCache(cache_dir)
        cache.load()
        print(f"Cache stats: {cache.stats()}")
        return

    # P2: Export traces: --export-traces
    if "--export-traces" in sys.argv:
        config = AgentConfig()
        from .tracing import AgentTracer
        span_dir = config.workspace_path / config.trace_dir_spans
        tracer = AgentTracer(trace_dir=span_dir)
        tracer.export_all()
        print(f"Traces exported to: {span_dir / 'spans.json'}")
        return

    config = AgentConfig()

    # Detect first run
    is_first_run = not (config.workspace_path / ".env").exists()

    if "--cli" in sys.argv:
        _run_cli(config, is_first_run=is_first_run)
    else:
        _run_tui(config, is_first_run=is_first_run)


def _create_agent(config: AgentConfig) -> CodingAgent:
    """Create a CodingAgent, optionally with MCP bridge."""
    if config.mcp_enabled:
        from .mcp import MCPBridge
        bridge = MCPBridge(config.workspace_path)
    else:
        bridge = None
    return CodingAgent(config, mcp_bridge=bridge)


def _print_workspace_tree(workspace: Path) -> None:
    """Print a compact semantic tree of the workspace."""
    config = WorkspaceStructureConfig.load(workspace)
    walker = SemanticTreeWalker(workspace, config)
    root = walker.walk()
    renderer = SemanticTreeRenderer(root, mode="summary", max_depth=2)
    console_text = renderer.render()
    if console_text:
        print(console_text)
        print()


def _run_cli(config: AgentConfig, *, is_first_run: bool = False) -> None:
    """Simple CLI mode: read prompts from stdin, print responses to stdout."""
    agent = _create_agent(config)

    # Print welcome screen
    print_welcome(
        mode="cli",
        workspace=config.workspace_path,
        model=config.primary_model,
        skills_count=len(agent._skills) if agent._skills else 0,
        is_first_run=is_first_run,
    )

    # Print workspace tree
    _print_workspace_tree(config.workspace_path)

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


def _run_tui(config: AgentConfig, *, is_first_run: bool = False) -> None:
    """Launch the Textual TUI."""
    from .tui.app import CodingAgentApp

    # Print welcome screen before TUI
    print_welcome(
        mode="tui",
        workspace=config.workspace_path,
        model=config.primary_model,
        is_first_run=is_first_run,
    )

    # Print workspace tree
    _print_workspace_tree(config.workspace_path)

    agent = _create_agent(config)
    app = CodingAgentApp(agent)
    app.run()


if __name__ == "__main__":
    main()

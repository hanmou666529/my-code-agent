"""CLI/TUI entry point for the coding agent.

Usage:
    python -m my_code_agent          # Launch Textual TUI
    python -m my_code_agent --cli    # CLI mode (stdin/stdout)
    python -m my_code_agent --welcome # Show welcome screen and exit
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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
    # Temporarily disable TUI mode so chunk_callback renders plainly
    import builtins

    original_print = builtins.print

    def _plain_print(*args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("flush", True)
        original_print(*args, **kwargs)

    builtins.print = _plain_print

    try:
        _run_cli_inner(config, is_first_run=is_first_run)
    finally:
        builtins.print = original_print


def _run_cli_inner(config: AgentConfig, *, is_first_run: bool = False) -> None:
    """CLI loop with animated dots, elapsed time, and token stats."""
    import time
    import threading

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

    def _erase_loading() -> None:
        if sys.stdout.isatty():
            sys.stdout.write("\r\x1b[K")
        else:
            sys.stdout.write("\n")
        sys.stdout.flush()

    _progress_bar_width = 30
    # ┬ animation frames
    _dot_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    # Shared state for the spinner thread
    _start_time: float = 0.0
    _stop_spinner: threading.Event = threading.Event()
    _spinner_thread: threading.Thread | None = None

    def _format_elapsed(seconds: float) -> str:
        """Format seconds into m s."""
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}m {s}s"

    def _spinner_loop() -> None:
        """Render animated dots during initial wait (before agent starts)."""
        frame_idx = 0
        while not _stop_spinner.is_set():
            symbol = _dot_frames[frame_idx % len(_dot_frames)]
            frame_idx += 1
            display = f"  {symbol}  Thinking…"
            sys.stdout.write(f"\r\x1b[K{display}")
            sys.stdout.flush()
            _stop_spinner.wait(0.1)

    def _render_progress(step: int, max_step: int, phase: str) -> None:
        """Render progress bar on top of the spinner."""
        pct = min(step / max_step, 1.0)
        filled = int(_progress_bar_width * pct)
        bar = "█" * filled + "░" * (_progress_bar_width - filled)
        phase_labels = {"thinking": "🧠 思考中", "action": "⚡ 执行中"}
        label = phase_labels.get(phase, phase)
        elapsed_str = _format_elapsed(time.monotonic() - _start_time)
        # Read token stats from agent (set by _call_llm after each LLM call)
        tok_in = getattr(agent, "_last_prompt_tokens", 0) or 0
        tok_out = getattr(agent, "_last_completion_tokens", 0) or 0
        token_part = ""
        if tok_out > 0:
            token_part = f" · ↑ {tok_out / 1024:.1f}k tokens"
        if sys.stdout.isatty():
            sys.stdout.write(f"\r\x1b[K  [{bar}] {label} 步骤 {step}/{max_step}  {elapsed_str}{token_part}")
            sys.stdout.flush()
        else:
            sys.stdout.write(f"\r\x1b[K  [{bar}] {label} 步骤 {step}/{max_step}  {elapsed_str}{token_part}\n")
            sys.stdout.flush()

    def _stop_spinner_thread() -> None:
        _stop_spinner.set()
        if _spinner_thread is not None:
            _spinner_thread.join(timeout=1.0)
        _erase_loading()

    for line in sys.stdin:
        prompt = line.strip()
        if not prompt:
            continue
        if prompt.lower() in ("quit", "exit", "q"):
            break

        print(f"\n> {prompt}")

        # Reset state
        _stop_spinner.clear()
        _start_time = time.monotonic()

        # Start spinner thread
        _stop_spinner_thread()  # join any previous
        _stop_spinner.clear()
        _spinner_thread = threading.Thread(target=_spinner_loop, daemon=True)
        _spinner_thread.start()

        # Capture agent output via chunk callback
        _output_chunks: list[str] = []
        _chunk_lock = threading.Lock()

        def _chunk_callback(text: str) -> None:
            with _chunk_lock:
                _output_chunks.append(text)

        agent._chunk_callback = _chunk_callback
        agent._step_callback = _render_progress
        # Hook token stats into the display
        agent._token_callback = lambda prompt_tok, completion_tok: (
            None  # captured by _render_progress via agent._last_*
        )

        try:
            response = agent.run(prompt)
        except Exception as e:
            response = f"[ERROR] {e}"
        finally:
            _stop_spinner.set()
            if _spinner_thread is not None:
                _spinner_thread.join(timeout=1.0)
            _erase_loading()
            if sys.stdout.isatty():
                sys.stdout.write("\r\x1b[K\n")
            else:
                sys.stdout.write("\n")
            sys.stdout.flush()

            # Final summary line with elapsed time and tokens
            elapsed = time.monotonic() - _start_time
            elapsed_str = _format_elapsed(elapsed)
            tok_in = getattr(agent, "_last_prompt_tokens", 0) or 0
            tok_out = getattr(agent, "_last_completion_tokens", 0) or 0
            tok_out_k = f"{tok_out / 1024:.1f}k" if tok_out > 0 else ""
            if tok_out_k:
                sys.stdout.write(f"\n  {elapsed_str} · ↑ {tok_out_k} tokens\n")
            else:
                sys.stdout.write(f"\n  {elapsed_str}\n")
            sys.stdout.flush()

            print(f"< {response}")
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

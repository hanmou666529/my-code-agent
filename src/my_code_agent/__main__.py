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
    """CLI loop with animated spinner, thinking preview, elapsed time, and tokens.

    Single display line — overwrites with \\r:
      ┬  0m 3s · ↑ 6.4k tokens     (idle / thinking)
      [████░░░░] 🧠 思考中 步骤 3/25  0m 12s · ↑ 3.2k tokens   (progress bar)
      思考: reading src/agent.py to understand...  (thinking preview)
    """
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

    # --- Shared mutable state (protected by _display_lock for safety) ---
    _display_lock = threading.Lock()
    _start_time: float = 0.0
    _stop_spinner: threading.Event = threading.Event()

    # Current display state
    _state_bar: str = ""          # progress bar text, e.g. "[██░] 🧠 思考中 步骤 3/25"
    _state_thought: str = ""      # live thinking preview (first 60 chars of streamed text)
    _state_tokens_in: int = 0
    _state_tokens_out: int = 0
    _state_phase: str = ""        # "thinking", "action", or ""

    _progress_bar_width = 30
    _dot_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def _format_elapsed(seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}m {s}s"

    def _draw_line() -> None:
        """Re-render the single-line status to stdout."""
        with _display_lock:
            bar = _state_bar
            thought = _state_thought
            tok_in = _state_tokens_in
            tok_out = _state_tokens_out
            phase = _state_phase

        elapsed = time.monotonic() - _start_time
        elapsed_str = _format_elapsed(elapsed)
        tok_str = f" · ↑ {tok_out / 1024:.1f}k tokens" if tok_out > 0 else ""

        if bar:
            # Progress bar mode
            display = f"  {bar}  {elapsed_str}{tok_str}"
        elif thought:
            # Thinking preview mode — show the first chunk of the LLM response
            display = f"  思考: {thought}"
        else:
            # Idle spinner
            display = f"  ┬  {elapsed_str}{tok_str}"

        sys.stdout.write(f"\r\x1b[K{display}")
        sys.stdout.flush()

    def _spinner_loop() -> None:
        """Continuously redraw the status line at ~8fps."""
        frame_idx = 0
        while not _stop_spinner.is_set():
            symbol = _dot_frames[frame_idx % len(_dot_frames)]
            frame_idx += 1

            elapsed = time.monotonic() - _start_time
            elapsed_str = _format_elapsed(elapsed)

            with _display_lock:
                bar = _state_bar
                thought = _state_thought
                tok_in = _state_tokens_in
                tok_out = _state_tokens_out

            tok_str = f" · ↑ {tok_out / 1024:.1f}k tokens" if tok_out > 0 else ""

            if bar:
                display = f"  {bar}  {elapsed_str}{tok_str}"
            elif thought:
                display = f"  思考: {thought}"
            else:
                display = f"  {symbol}  {elapsed_str}{tok_str}"

            sys.stdout.write(f"\r\x1b[K{display}")
            sys.stdout.flush()
            _stop_spinner.wait(0.125)  # 8Hz

    def _render_progress(step: int, max_step: int, phase: str) -> None:
        """Callback invoked at the start of each ReAct step."""
        with _display_lock:
            pct = min(step / max_step, 1.0)
            filled = int(_progress_bar_width * pct)
            bar = "█" * filled + "░" * (_progress_bar_width - filled)
            phase_labels = {"thinking": "🧠 思考中", "action": "⚡ 执行中"}
            label = phase_labels.get(phase, phase)
            _state_bar = f"[{bar}] {label} 步骤 {step}/{max_step}"
            _state_phase = phase
            _state_thought = ""  # clear thinking preview while showing bar

    def _update_thought(preview: str) -> None:
        """Called from chunk_callback to show the thinking preview."""
        with _display_lock:
            # Show first 60 chars, stripped of Thought:/Action: prefixes
            text = preview.replace("Thought: ", "").replace("Thought:", "").strip()
            if len(text) > 60:
                text = text[:57] + "…"
            _state_thought = text

    def _update_tokens(prompt_tok: int, completion_tok: int) -> None:
        """Called after each LLM call to update token stats."""
        with _display_lock:
            _state_tokens_in = prompt_tok
            _state_tokens_out = completion_tok

    # --- Per-prompt loop ---
    for line in sys.stdin:
        prompt = line.strip()
        if not prompt:
            continue
        if prompt.lower() in ("quit", "exit", "q"):
            break

        print(f"\n> {prompt}")

        # Reset display state
        _stop_spinner.set()
        _stop_spinner.clear()
        with _display_lock:
            _start_time = time.monotonic()
            _state_bar = ""
            _state_thought = ""
            _state_tokens_in = 0
            _state_tokens_out = 0
            _state_phase = ""

        # Start spinner thread
        _spinner_thread = threading.Thread(target=_spinner_loop, daemon=True)
        _spinner_thread.start()

        # Capture agent output
        _output_chunks: list[str] = []
        _chunk_lock = threading.Lock()
        _first_chunk = threading.Event()  # signal first token received

        def _chunk_callback(text: str) -> None:
            with _chunk_lock:
                _output_chunks.append(text)
            # On first chunk, update thinking preview
            if not _first_chunk.is_set():
                _first_chunk.set()
                _update_thought(text)

        agent._chunk_callback = _chunk_callback
        agent._step_callback = _render_progress

        # Token stats hook
        def _token_hook(prompt_tok: int, completion_tok: int) -> None:
            _update_tokens(prompt_tok, completion_tok)

        agent._token_callback = _token_hook

        try:
            response = agent.run(prompt)
        except Exception as e:
            response = f"[ERROR] {e}"
        finally:
            _stop_spinner.set()
            _spinner_thread.join(timeout=1.0)

            with _display_lock:
                tok_in = _state_tokens_in
                tok_out = _state_tokens_out

            # Clear the line and draw final summary
            sys.stdout.write("\r\x1b[K\n")
            elapsed = time.monotonic() - _start_time
            elapsed_str = _format_elapsed(elapsed)
            if tok_out > 0:
                sys.stdout.write(f"\n  {elapsed_str} · ↑ {tok_out / 1024:.1f}k tokens\n")
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

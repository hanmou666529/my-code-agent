"""Welcome screen and banner for the Coding Agent CLI.

Displays an ASCII art logo, version info, model status, and quick-start hints
when the agent launches. Adapts to terminal width and respects NO_COLOR.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from . import __version__

# ---------------------------------------------------------------------------
# ASCII Art Logo — 20 lines, 48 chars wide at full resolution
# ---------------------------------------------------------------------------

_LOGO_LINES: list[str] = [
    " ██████╗██╗  ██╗███████╗    ██████╗ ███████╗    ██████╗  ██████╗ ███╗   ██╗",
    "██╔════╝██║  ██║██╔════╝    ██╔══██╗██╔════╝    ██╔═══██╗██╔═══██╗████╗  ██║",
    "██║     ███████║█████╗      ██████╔╝███████╗    ██║   ██║██║   ██║██╔██╗ ██║",
    "██║     ██╔══██║██╔══╝      ██╔══██╗██╔════╝    ██║   ██║██║   ██║██║╚██╗██║",
    "╚██████╗██║  ██║███████╗    ██║  ██║███████╗    ╚██████╔╝╚██████╔╝██║ ╚████║",
    " ╚═════╝╚═╝  ╚═╝╚══════╝    ╚═╝  ╚═╝╚══════╝     ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝",
]

# Subtitle rendered below the logo
_SUBTITLE = "Autonomous Coding Agent"

# Quick-start hints shown in a bordered panel
_QUICK_START: list[str] = [
    '[bold cyan]$ agent[/] "Refactor auth module"',
    '[bold cyan]$ agent --skill[/] [green]refactor-function[/]',
    '[bold cyan]$ agent --status[/]',
    '[bold cyan]$ agent --help[/]',
]

# What to show depending on mode
_WELCOME_MESSAGES: dict[str, str] = {
    "first_run": (
        "Welcome! This is your first time running the Coding Agent.\n"
        "Set your [bold]ANTHROPIC_API_KEY[/] in [.env] to get started."
    ),
    "ready": "Ready. Type a task or use [bold]--skill[/] to run a specific skill.",
    "mcp_enabled": "MCP mode active. Skills loaded from [dim].mcp/skills.json[/].",
}


def _is_no_color() -> bool:
    """Check NO_COLOR env var (RFC 2044)."""
    return os.environ.get("NO_COLOR", "") != ""


def _detect_theme() -> str:
    """Detect light/dark terminal theme for adaptive colors."""
    term_color_support = os.environ.get("COLORTERM", "")
    if term_color_support in ("truecolor", "24bit"):
        return "dark"  # truecolor implies dark-capable terminal
    return "dark"  # default to dark theme


def _fit_logo_width(console_width: int) -> int:
    """Calculate max logo width that fits the console with padding."""
    # Reserve 6 chars for left/right padding in the panel
    max_logo = console_width - 6
    # Full logo is 48 chars; minimum acceptable is 36
    return max(36, min(48, max_logo))


def _build_logo_text(max_width: int, no_color: bool) -> Text:
    """Build the ASCII art logo as a Rich Text object, scaled to width."""
    full_width = 48
    if max_width >= full_width:
        lines = _LOGO_LINES
    else:
        ratio = max_width / full_width
        lines = []
        for line in _LOGO_LINES:
            kept = max(1, int(len(line) * ratio))
            lines.append(line[:kept])

    color = "" if no_color else "#00D4FF"
    t = Text()
    for i, line in enumerate(lines):
        if i > 0:
            t.append("\n")
        if no_color:
            t.append(line)
        else:
            t.append(line, style=f"bold {color}")
    return t


def _build_subtitle(no_color: bool) -> Text:
    """Build the subtitle text below the logo."""
    if no_color:
        return Text(f"  {_SUBTITLE}  v{__version__}")
    return Text("  ", style="dim") + Text(
        f"{_SUBTITLE}  v{__version__}",
        style="bold cyan",
    )


def _build_quick_start_panel(no_color: bool) -> Panel:
    """Build the quick-start hints panel."""
    lines: list[Text] = [
        Text("  Quick Start", style="bold yellow"),
        Text("  " + "-" * 38, style="dim"),
    ]
    for cmd in _QUICK_START:
        if no_color:
            lines.append(Text(f"  {cmd}"))
        else:
            lines.append(Text(f"  {cmd}"))
    return Panel(
        Text("\n").join(lines),
        border_style="dim" if no_color else "blue",
        padding=(0, 1),
    )


def _build_status_line(
    workspace: Optional[Path] = None,
    model: Optional[str] = None,
    skills_count: int = 0,
    no_color: bool = False,
) -> Text:
    """Build the bottom status bar with runtime info."""
    parts: list[str | Text] = []

    if workspace:
        parts.append(Text("📂 ", style="dim"))
        parts.append(Text(f" {workspace.resolve()}", style="dim italic"))

    if model:
        parts.append(Text("  🧠 ", style="dim"))
        parts.append(Text(model, style="cyan"))

    if skills_count > 0:
        parts.append(Text("  ⚡ ", style="dim"))
        parts.append(Text(f"{skills_count} skills", style="green"))

    parts.append(Text("  🕐 ", style="dim"))
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    parts.append(Text(now, style="dim"))

    return Text(" ").join(parts)


def print_welcome(
    mode: str = "cli",
    workspace: Optional[Path] = None,
    model: Optional[str] = None,
    skills_count: int = 0,
    is_first_run: bool = False,
) -> None:
    """Print the full welcome screen to stdout.

    Args:
        mode: "cli" or "tui" — controls which welcome message to show.
        workspace: Current workspace path (shown in status bar).
        model: Active model name (shown in status bar).
        skills_count: Number of loaded skills (shown in status bar).
        is_first_run: If True, show first-run setup hint.
    """
    # Use Windows-compatible color system when available
    color_system: Optional[str]
    if no_color := _is_no_color():
        color_system = None
    elif sys.platform == "win32":
        # Windows 10+ supports ANSI; Rich auto-detects in most cases
        color_system = "auto"
    else:
        color_system = "auto"

    console = Console(force_terminal=True, color_system=color_system)
    term_width = console.size.width if console.size.width > 0 else 80

    # 1. ASCII Art Logo
    logo_width = _fit_logo_width(term_width)
    logo_text = _build_logo_text(logo_width, no_color)
    console.print(logo_text)

    # 2. Subtitle
    console.print(_build_subtitle(no_color))
    console.print()

    # 3. Welcome message
    msg_key = "first_run" if is_first_run else ("mcp_enabled" if skills_count > 0 else "ready")
    welcome_msg = _WELCOME_MESSAGES[msg_key]
    if mode == "tui":
        welcome_msg += "\nPress [bold]Ctrl+C[/] to switch to CLI mode."
    console.print(Text(welcome_msg))
    console.print()

    # 4. Quick-start panel (only in CLI mode or on first run)
    if mode == "cli" or is_first_run:
        console.print(_build_quick_start_panel(no_color))
        console.print()

    # 5. Status bar
    status = _build_status_line(workspace, model, skills_count, no_color)
    console.print(status)

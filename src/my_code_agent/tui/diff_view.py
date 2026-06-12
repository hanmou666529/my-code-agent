"""Diff preview widget for the coding agent TUI.

Renders a diff of proposed file edits using Rich's Diff renderable.
"""

from __future__ import annotations

from textual.reactive import reactive
from textual.widget import Widget
from textual.types import RenderableType
from rich.diff import Diff


class DiffPreview(Widget):
    """Render a diff preview of a proposed file edit."""

    DEFAULT_CSS = """
    DiffPreview {
        height: auto;
        border: solid $accent;
        margin: 1 0;
        padding: 1;
    }
    """

    old_content: reactive[str] = reactive("")
    new_content: reactive[str] = reactive("")

    def render(self) -> RenderableType:
        if not self.old_content or not self.new_content:
            return "[No diff available]"
        return Diff(self.old_content.splitlines(), self.new_content.splitlines())

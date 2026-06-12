"""Confirmation modal dialog for the coding agent TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmScreen(ModalScreen[bool]):
    """Modal confirmation dialog for agent actions."""

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
        background: $primary 40%;
    }
    #confirm-dialog {
        width: 50;
        height: auto;
        background: $surface;
        border: solid $accent;
        padding: 2;
        layout: grid;
        grid-size: 1;
        grid-rows: auto auto auto;
    }
    """

    def __init__(self, message: str, confirm_label: str = "Confirm") -> None:
        super().__init__()
        self._message = message
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        yield Container(
            Label(self._message, id="confirm-message"),
            Horizontal(
                Button(self._confirm_label, variant="primary", id="confirm"),
                Button("Cancel", variant="secondary", id="cancel"),
                id="confirm-buttons",
            ),
            id="confirm-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dismiss with True for confirm, False for cancel."""
        if event.button.id == "confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)

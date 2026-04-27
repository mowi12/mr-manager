"""Unsaved-changes modal UI component."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class UnsavedChangesModal(ModalScreen[bool]):
    """Modal that confirms quitting when unsaved changes are present."""

    def compose(self) -> ComposeResult:
        """Compose the unsaved-changes quit confirmation dialog."""
        with Vertical(id="unsaved-changes-dialog"):
            yield Static(
                "You Have Unsaved Changes.\nQuit Without Saving?",
                id="unsaved-changes-message",
            )
            with Horizontal(id="unsaved-changes-actions"):
                yield Button("Go Back", id="unsaved-go-back", variant="primary")
                yield Button("I'm Sure", id="unsaved-confirm-quit", variant="error")

    def on_mount(self) -> None:
        """Focus the safe default action when the modal opens."""
        self.query_one("#unsaved-go-back", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle dialog button presses.

        Args:
            event: Button press event.
        """
        self.dismiss(event.button.id == "unsaved-confirm-quit")

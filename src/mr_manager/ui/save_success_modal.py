"""Save-success modal UI component."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class SaveSuccessModal(ModalScreen[bool]):
    """Modal shown after saving configuration changes."""

    def __init__(self, message: str) -> None:
        """Initialize modal with a status message.

        Args:
            message: Message shown in the save status dialog.
        """
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        """Compose the save-success confirmation dialog."""
        with Vertical(id="save-success-dialog"):
            yield Static(self._message, id="save-success-message")
            with Horizontal(id="save-success-actions"):
                yield Button("Continue", id="save-go-back", variant="primary")
                yield Button("Quit", id="save-quit")

    def on_mount(self) -> None:
        """Focus the safe default action when the modal opens."""
        self.query_one("#save-go-back", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle save-success dialog button presses.

        Args:
            event: Button press event.
        """
        self.dismiss(event.button.id == "save-quit")

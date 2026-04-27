"""Reusable action modal UI component."""

from __future__ import annotations

from typing import Literal

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

ButtonVariant = Literal["default", "primary", "success", "warning", "error"]
FocusTarget = Literal["cancel", "confirm"]


class ActionModal(ModalScreen[bool]):
    """Configurable modal with cancel/confirm actions."""

    def __init__(
        self,
        *,
        message: str,
        cancel_label: str,
        confirm_label: str,
        cancel_variant: ButtonVariant = "default",
        confirm_variant: ButtonVariant = "default",
        focus_target: FocusTarget = "cancel",
    ) -> None:
        """Initialize modal content and button configuration.

        Args:
            message: Main modal message text.
            cancel_label: Label for the cancel action button.
            confirm_label: Label for the confirm action button.
            cancel_variant: Textual button variant for cancel action.
            confirm_variant: Textual button variant for confirm action.
            focus_target: Button focused initially when modal opens.
        """
        super().__init__()
        self._message = message
        self._cancel_label = cancel_label
        self._confirm_label = confirm_label
        self._cancel_variant = cancel_variant
        self._confirm_variant = confirm_variant
        self._focus_target = focus_target

    def compose(self) -> ComposeResult:
        """Compose the configurable action dialog."""
        with Vertical(id="action-modal-dialog"):
            yield Static(self._message, id="action-modal-message")
            with Horizontal(id="action-modal-actions"):
                yield Button(
                    self._cancel_label,
                    id="action-modal-cancel",
                    variant=self._cancel_variant,
                )
                yield Button(
                    self._confirm_label,
                    id="action-modal-confirm",
                    variant=self._confirm_variant,
                )

    def on_mount(self) -> None:
        """Focus the configured default action when the modal opens."""
        target_button_id = "#action-modal-cancel"
        if self._focus_target == "confirm":
            target_button_id = "#action-modal-confirm"
        self.query_one(target_button_id, Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Dismiss with True only when the confirm action was chosen.

        Args:
            event: Button press event.
        """
        self.dismiss(event.button.id == "action-modal-confirm")

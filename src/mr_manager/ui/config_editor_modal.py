"""Modal for editing user-configurable mr-manager settings."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label

from mr_manager.core.user_config import UserConfig


class ConfigEditorModal(ModalScreen[UserConfig | None]):
    """UI modal for editing persistent user configuration values."""

    def __init__(self, user_config: UserConfig) -> None:
        """Initialize modal with current config values.

        Args:
            user_config: Current user configuration shown as editable defaults.
        """
        super().__init__()
        self._user_config = user_config

    def compose(self) -> ComposeResult:
        """Compose config editor form fields and actions."""
        with Vertical(id="config-editor-dialog"):
            yield Label("Configuration", id="config-editor-title")
            yield Label("Repository Discovery Root", id="config-root-label")
            yield Input(
                value=str(self._user_config.discovery_root),
                id="config-root-input",
                placeholder="/path/to/scan",
            )
            yield Label("Discovery Cache TTL (hours)", id="config-cache-ttl-label")
            yield Input(
                value=str(self._user_config.discovery_cache_ttl_hours),
                id="config-cache-ttl-input",
                placeholder="24",
            )
            yield Label("", id="config-editor-error")
            with Horizontal(id="config-editor-actions"):
                yield Button("Cancel", id="config-cancel", variant="default")
                yield Button("Save", id="config-save", variant="primary")

    def on_mount(self) -> None:
        """Focus first field when config editor opens."""
        self.query_one("#config-root-input", Input).focus()

    def _show_validation_error(self, message: str) -> None:
        """Render inline validation error text in the modal."""
        self.query_one("#config-editor-error", Label).update(message)

    def _build_user_config_from_inputs(self) -> UserConfig | None:
        """Validate form values and build user config when valid."""
        root_raw = self.query_one("#config-root-input", Input).value.strip()
        ttl_raw = self.query_one("#config-cache-ttl-input", Input).value.strip()
        if not root_raw:
            self._show_validation_error("Discovery root is required.")
            return None
        try:
            ttl_hours = int(ttl_raw)
        except ValueError:
            self._show_validation_error("Cache TTL must be an integer.")
            return None
        if ttl_hours <= 0:
            self._show_validation_error("Cache TTL must be greater than 0.")
            return None
        discovery_root = Path(root_raw).expanduser().resolve(strict=False)
        return UserConfig(
            discovery_cache_ttl_hours=ttl_hours,
            discovery_root=discovery_root,
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle cancel/save actions and return result to caller.

        Args:
            event: Button press event.
        """
        if event.button.id == "config-cancel":
            self.dismiss(None)
            return
        if event.button.id != "config-save":
            return
        updated_config = self._build_user_config_from_inputs()
        if updated_config is None:
            return
        self.dismiss(updated_config)

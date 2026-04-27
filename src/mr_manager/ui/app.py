"""Textual UI for selecting repositories to add or remove."""

from __future__ import annotations

from pathlib import Path

from rich.cells import cell_len
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Label, LoadingIndicator, OptionList, Static

from mr_manager.ui.action_modal import ActionModal
from mr_manager.ui.selection.controller import RepositorySelectionController
from mr_manager.ui.selection.model import RepositorySelectionModel

_TOGGLED_BULLET_COLOR = "#fca311"


class MrManagerApp(App[None]):
    """Single-view app to toggle repository membership in myrepos config."""

    TITLE = "mr-manager"
    CSS_PATH = "ui.tcss"

    BINDINGS = [
        ("space", "toggle_selected", "Toggle"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("s", "save", "Save"),
        ("r", "refresh_scan", "Refresh Scan"),
        Binding("q,escape", "quit_without_saving", "Quit", key_display="q/ESC"),
    ]

    def __init__(self) -> None:
        """Initialize UI controller and state."""
        super().__init__()
        self._controller = RepositorySelectionController()

    @property
    def _model(self) -> RepositorySelectionModel:
        """Return the mutable state model used by the UI."""
        return self._controller.model

    def compose(self) -> ComposeResult:
        """Compose the app layout widgets."""
        yield Header(show_clock=False, icon="")
        with Vertical(id="content"):
            with Horizontal(id="scan-status-row"):
                yield Static(f"Scanning: {self._model.discover_root}", id="scan-path")
                with Horizontal(id="scan-state"):
                    yield LoadingIndicator(id="scan-state-indicator")
                    yield Label("", id="scan-state-result")
            yield OptionList(id="repo-list")
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        """Initialize widgets and start asynchronous repository loading."""
        repo_list = self.query_one("#repo-list", OptionList)
        repo_list.disabled = True
        self.query_one("#scan-state-result", Label).display = False
        self.load_repository_data()

    def on_resize(self, _: events.Resize) -> None:
        """Re-evaluate scan status layout whenever terminal size changes."""
        self._apply_scan_state_layout()

    @work(thread=True, exclusive=True)
    def load_repository_data(self, force_scan: bool = False) -> None:
        """Load discovered repositories and configured repo sections in a worker."""
        try:
            discovered, sections_by_path = self._controller.load_repository_data(force_scan)
        except (OSError, UnicodeDecodeError, RuntimeError, ValueError) as error:
            self.call_from_thread(self._handle_repository_load_error, error)
        else:
            self.call_from_thread(self._set_repository_data, discovered, sections_by_path)

    def _set_repository_data(
        self, discovered: list[Path], sections_by_path: dict[Path, list[str]]
    ) -> None:
        """Apply loaded repository and config data to UI state."""
        self._controller.apply_repository_data(discovered, sections_by_path)
        self._model.loading = False
        self.query_one("#scan-state-indicator", LoadingIndicator).display = False
        self.query_one("#scan-state-result", Label).display = True
        self._render_repository_list()
        self._update_scan_state_result()

    def _handle_repository_load_error(self, error: Exception) -> None:
        """Handle repository load failures from the worker thread."""
        self._model.loading = False
        self.query_one("#scan-state-indicator", LoadingIndicator).display = False
        error_label = self.query_one("#scan-state-result", Label)
        error_label.display = True
        self._set_scan_state_text(
            full=f"Error Loading Repositories: {error}",
            compact="Error Loading Repositories.",
        )
        self.query_one("#repo-list", OptionList).disabled = True

    def _render_repository_list(self) -> None:
        """Render repository options into the selectable list widget."""
        repo_list = self.query_one("#repo-list", OptionList)
        repo_list.clear_options()
        for repo in self._model.displayed_repos:
            repo_list.add_option(self._render_repo_prompt(repo))
        repo_list.disabled = not self._model.displayed_repos
        if self._model.displayed_repos:
            repo_list.highlighted = 0
            repo_list.focus()

    def _render_repo_prompt(self, repo: Path) -> Text:
        """Render a single repository row with selected/unselected bullet."""
        if self._controller.is_missing_or_unreachable(repo):
            bullet = "◐" if repo in self._model.selected_repo_paths else "◌"
        else:
            bullet = "●" if repo in self._model.selected_repo_paths else "○"
        bullet_style = _TOGGLED_BULLET_COLOR if self._controller.is_repo_toggled(repo) else None
        prompt = Text()
        prompt.append(bullet, style=bullet_style)
        prompt.append(f" {repo}")
        return prompt

    def _toggle_repo_by_index(self, index: int) -> None:
        """Toggle selected state for a repository at list index."""
        toggled_repo = self._controller.toggle_repo_by_index(index)
        if toggled_repo is None:
            return

        self.query_one("#repo-list", OptionList).replace_option_prompt_at_index(
            index,
            self._render_repo_prompt(toggled_repo),
        )
        self._update_scan_state_result()

    def _update_scan_state_result(self) -> None:
        """Update the top-right scan/result summary text."""
        if not self._model.displayed_repos:
            self._set_scan_state_text(
                full=f"No Git repositories found under {self._model.discover_root}.",
                compact="No Git repositories found.",
            )
            return

        add_count = len(self._controller.repos_to_add())
        remove_count = len(self._controller.repos_to_remove())
        missing_count = len(self._model.configured_repo_paths - self._model.discovered_repo_set())
        self._set_scan_state_text(
            full=(
                "Discovered: "
                f"{len(self._model.discovered_repos)} | Missing: {missing_count} | "
                f"To Add: {add_count} | To Remove: {remove_count}"
            ),
            compact=(
                f"D:{len(self._model.discovered_repos)} | M:{missing_count} | "
                f"+:{add_count} | -:{remove_count}"
            ),
        )

    def _set_scan_state_text(self, *, full: str, compact: str | None = None) -> None:
        """Set scan status text variants and apply responsive layout."""
        self._model.scan_state_text = full
        self._model.scan_state_text_compact = compact
        self._apply_scan_state_layout()

    def _apply_scan_state_layout(self) -> None:
        """Switch scan status between one-row and stacked layouts when needed."""
        if not self.is_mounted:
            return

        status_label = self.query_one("#scan-state-result", Label)
        scan_row = self.query_one("#scan-status-row", Horizontal)
        scan_state = self.query_one("#scan-state", Horizontal)
        indicator = self.query_one("#scan-state-indicator", LoadingIndicator)
        full_text = self._model.scan_state_text
        compact_text = self._model.scan_state_text_compact or full_text
        row_width = scan_row.size.width
        if row_width <= 0:
            return

        indicator_width = indicator.size.width if indicator.display else 0
        full_required_width = cell_len(full_text) + indicator_width
        compact_required_width = cell_len(compact_text) + indicator_width
        one_row_status_width = (
            scan_state.size.width if not scan_row.has_class("stacked") else max(1, row_width // 2)
        )
        stacked_status_width = row_width

        if full_required_width <= one_row_status_width:
            scan_row.remove_class("stacked")
            status_label.update(full_text)
            return

        if full_required_width <= stacked_status_width:
            scan_row.add_class("stacked")
            status_label.update(full_text)
            return

        scan_row.add_class("stacked")
        if compact_required_width <= stacked_status_width:
            status_label.update(compact_text)
            return

        status_label.update(compact_text)

    def action_cursor_down(self) -> None:
        """Move list selection one row down."""
        self.query_one("#repo-list", OptionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move list selection one row up."""
        self.query_one("#repo-list", OptionList).action_cursor_up()

    def action_toggle_selected(self) -> None:
        """Toggle currently highlighted repository selection."""
        if self._model.loading or not self._model.displayed_repos:
            return
        repo_list = self.query_one("#repo-list", OptionList)
        highlighted_index = repo_list.highlighted
        if highlighted_index is None:
            return
        self._toggle_repo_by_index(highlighted_index)

    def _sync_config_state_after_save(self) -> bool:
        """Refresh configured state from disk after writing the config."""
        try:
            self._controller.refresh_config_state_after_save()
        except (OSError, UnicodeDecodeError) as error:
            self.log(f"Failed to refresh config from disk after save: {error!r}")
            self._set_scan_state_text(
                full=f"Changes Saved, But Reload Failed: {error}",
                compact="Changes Saved, Reload Failed.",
            )
            return False

        self._render_repository_list()
        self._update_scan_state_result()
        return True

    def _handle_action_modal_result(self, should_quit: bool | None) -> None:
        """Process action modal result and keep focus when continuing."""
        if should_quit:
            self.exit()
            return
        if self._model.displayed_repos and not self._model.loading:
            self.query_one("#repo-list", OptionList).focus()

    def action_save(self) -> None:
        """Save pending config changes and display success options."""
        if self._model.loading:
            return
        has_changes = self._controller.has_unsaved_changes()
        if has_changes:
            self._controller.save_changes()
            state_synced = self._sync_config_state_after_save()
            message = (
                "Changes Saved Successfully." if state_synced else "Changes Saved. Reload Failed."
            )
        else:
            message = "No Changes To Save."
        self.push_screen(
            ActionModal(
                message=message,
                cancel_label="Continue",
                confirm_label="Quit",
                cancel_variant="primary",
                focus_target="cancel",
            ),
            self._handle_action_modal_result,
        )

    def action_refresh_scan(self) -> None:
        """Force a fresh filesystem scan and bypass the cache."""
        if self._model.loading:
            return

        self._model.loading = True
        self.query_one("#repo-list", OptionList).disabled = True

        scan_state_result = self.query_one("#scan-state-result", Label)
        scan_state_result.display = False
        self.query_one("#scan-state-indicator", LoadingIndicator).display = True

        self._set_scan_state_text(
            full=f"Scanning: {self._model.discover_root}",
            compact="Scanning...",
        )
        self.load_repository_data(force_scan=True)

    def action_quit_without_saving(self) -> None:
        """Exit immediately or ask for confirmation when unsaved changes exist."""
        if not self._controller.has_unsaved_changes():
            self.exit()
            return
        self.push_screen(
            ActionModal(
                message="You Have Unsaved Changes.\nQuit Without Saving?",
                cancel_label="Go Back",
                confirm_label="I'm Sure",
                cancel_variant="primary",
                confirm_variant="error",
                focus_target="cancel",
            ),
            self._handle_action_modal_result,
        )

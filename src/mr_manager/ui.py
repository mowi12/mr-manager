"""Textual UI for selecting repositories to add or remove."""

from __future__ import annotations

from pathlib import Path

from rich.cells import cell_len
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Label, LoadingIndicator, OptionList, Static

from mr_manager.cache import load_cached_repositories, save_cached_repositories
from mr_manager.config import parse_configured_repo_sections, write_config_updates
from mr_manager.discovery import discover_git_repositories

_TOGGLED_BULLET_COLOR = "#fca311"


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
        """Initialize application state for discovery, config, and selection."""
        super().__init__()
        self._discover_root = Path.home()
        self._config_path = Path.home() / ".mrconfig"
        self._discovered_repos: list[Path] = []
        self._displayed_repos: list[Path] = []
        self._repo_sections_by_path: dict[Path, list[str]] = {}
        self._configured_repo_paths: set[Path] = set()
        self._selected_repo_paths: set[Path] = set()
        self._loading = True
        self._scan_state_text = ""
        self._scan_state_text_compact: str | None = None

    def _discovered_repo_set(self) -> set[Path]:
        """Return discovered repositories as a set for membership checks."""
        return set(self._discovered_repos)

    def compose(self) -> ComposeResult:
        """Compose the app layout widgets."""
        yield Header(show_clock=False, icon="")
        with Vertical(id="content"):
            with Horizontal(id="scan-status-row"):
                yield Static(f"Scanning: {self._discover_root}", id="scan-path")
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
            sections_by_path = parse_configured_repo_sections(self._config_path)

            discovered = None
            if not force_scan:
                discovered = load_cached_repositories()

            if discovered is None:
                # Cache was missing, expired, or we forced a scan
                discovered = discover_git_repositories(self._discover_root)
                save_cached_repositories(discovered)

        except (OSError, UnicodeDecodeError, RuntimeError, ValueError) as error:
            self.call_from_thread(self._handle_repository_load_error, error)
        else:
            self.call_from_thread(self._set_repository_data, discovered, sections_by_path)

    def _set_repository_data(
        self, discovered: list[Path], sections_by_path: dict[Path, list[str]]
    ) -> None:
        """Apply loaded repository and config data to UI state.

        Args:
            discovered: Discovered repository paths from filesystem scan.
            sections_by_path: Mapping of configured repositories to section names.
        """
        self._discovered_repos = discovered
        discovered_set = set(discovered)
        self._repo_sections_by_path = sections_by_path
        self._configured_repo_paths = set(sections_by_path.keys())
        self._displayed_repos = sorted(
            discovered_set.union(self._configured_repo_paths),
            key=lambda repo: str(repo).lower(),
        )
        self._selected_repo_paths = set(self._configured_repo_paths)
        self._loading = False
        self.query_one("#scan-state-indicator", LoadingIndicator).display = False
        self.query_one("#scan-state-result", Label).display = True
        self._render_repository_list()
        self._update_scan_state_result()

    def _handle_repository_load_error(self, error: Exception) -> None:
        """Handle repository load failures from the worker thread.

        Args:
            error: Exception raised during discovery or config parsing.
        """
        self._loading = False
        self.query_one("#scan-state-indicator", LoadingIndicator).display = False
        error_label = self.query_one("#scan-state-result", Label)
        error_label.display = True
        self._set_scan_state_text(
            full=f"Error Loading Repositories: {error}",
            compact="Error Loading Repositories.",
        )
        repo_list = self.query_one("#repo-list", OptionList)
        repo_list.disabled = True

    def _render_repository_list(self) -> None:
        """Render repository options into the selectable list widget."""
        repo_list = self.query_one("#repo-list", OptionList)
        repo_list.clear_options()
        for repo in self._displayed_repos:
            repo_list.add_option(self._render_repo_prompt(repo))
        repo_list.disabled = not self._displayed_repos
        if self._displayed_repos:
            repo_list.highlighted = 0
            repo_list.focus()

    def _render_repo_prompt(self, repo: Path) -> Text:
        """Render a single repository row with selected/unselected bullet.

        Args:
            repo: Repository path to render.

        Returns:
            Display text for the repository list row.
        """
        if self._is_missing_or_unreachable(repo):
            bullet = "◐" if repo in self._selected_repo_paths else "◌"
        else:
            bullet = "●" if repo in self._selected_repo_paths else "○"
        bullet_style = _TOGGLED_BULLET_COLOR if self._is_repo_toggled(repo) else None
        prompt = Text()
        prompt.append(bullet, style=bullet_style)
        prompt.append(f" {repo}")
        return prompt

    def _is_repo_toggled(self, repo: Path) -> bool:
        """Return whether repository selection differs from persisted config."""
        is_selected = repo in self._selected_repo_paths
        is_configured = repo in self._configured_repo_paths
        return is_selected != is_configured

    def _is_missing_or_unreachable(self, repo: Path) -> bool:
        """Return whether a repo is configured but not found during discovery.

        Args:
            repo: Repository path to check.

        Returns:
            True when repo is configured but not present in discovered paths.
        """
        return repo in self._configured_repo_paths and repo not in self._discovered_repo_set()

    def _toggle_repo_by_index(self, index: int) -> None:
        """Toggle selected state for a repository at list index.

        Args:
            index: Zero-based repository index in the displayed list.
        """
        if index < 0 or index >= len(self._displayed_repos):
            return

        repo = self._displayed_repos[index]
        if repo in self._selected_repo_paths:
            self._selected_repo_paths.remove(repo)
        else:
            self._selected_repo_paths.add(repo)

        self.query_one("#repo-list", OptionList).replace_option_prompt_at_index(
            index,
            self._render_repo_prompt(repo),
        )
        self._update_scan_state_result()

    def _update_scan_state_result(self) -> None:
        """Update the top-right scan/result summary text."""
        if not self._displayed_repos:
            self._set_scan_state_text(
                full=f"No Git repositories found under {self._discover_root}.",
                compact="No Git repositories found.",
            )
            return

        discovered_set = self._discovered_repo_set()
        add_count = len(self._repos_to_add())
        remove_count = len(self._repos_to_remove())
        missing_count = len(self._configured_repo_paths - discovered_set)
        self._set_scan_state_text(
            full=(
                "Discovered: "
                f"{len(self._discovered_repos)} | Missing: {missing_count} | "
                f"To Add: {add_count} | To Remove: {remove_count}"
            ),
            compact=(
                f"D:{len(self._discovered_repos)} | M:{missing_count} | "
                f"+:{add_count} | -:{remove_count}"
            ),
        )

    def _set_scan_state_text(self, *, full: str, compact: str | None = None) -> None:
        """Set scan status text variants and apply responsive layout.

        Args:
            full: Full status text preferred for wider terminals.
            compact: Optional shortened variant for narrow terminals.
        """
        self._scan_state_text = full
        self._scan_state_text_compact = compact
        self._apply_scan_state_layout()

    def _apply_scan_state_layout(self) -> None:
        """Switch scan status between one-row and stacked layouts when needed."""
        if not self.is_mounted:
            return

        status_label = self.query_one("#scan-state-result", Label)
        scan_row = self.query_one("#scan-status-row", Horizontal)
        scan_state = self.query_one("#scan-state", Horizontal)
        indicator = self.query_one("#scan-state-indicator", LoadingIndicator)
        full_text = self._scan_state_text
        compact_text = self._scan_state_text_compact or full_text
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
        if self._loading or not self._displayed_repos:
            return
        repo_list = self.query_one("#repo-list", OptionList)
        highlighted_index = repo_list.highlighted
        if highlighted_index is None:
            return
        self._toggle_repo_by_index(highlighted_index)

    def _save_changes(self) -> None:
        """Persist selected repository additions/removals to config file."""
        repos_to_add = sorted(self._repos_to_add(), key=lambda repo: str(repo).lower())
        repos_to_remove = sorted(self._repos_to_remove(), key=lambda repo: str(repo).lower())
        section_names_to_remove = {
            section_name
            for repo in repos_to_remove
            for section_name in self._repo_sections_by_path.get(repo, [])
        }

        if repos_to_add or section_names_to_remove:
            write_config_updates(self._config_path, repos_to_add, section_names_to_remove)

    def _sync_config_state_after_save(self) -> bool:
        """Refresh configured state from disk after writing the config."""
        try:
            sections_by_path = parse_configured_repo_sections(self._config_path)
        except (OSError, UnicodeDecodeError) as error:
            self.log(f"Failed to refresh config from disk after save: {error!r}")
            self._set_scan_state_text(
                full=f"Changes Saved, But Reload Failed: {error}",
                compact="Changes Saved, Reload Failed.",
            )
            return False

        self._repo_sections_by_path = sections_by_path
        self._configured_repo_paths = set(sections_by_path.keys())
        self._displayed_repos = sorted(
            self._discovered_repo_set().union(self._configured_repo_paths),
            key=lambda repo: str(repo).lower(),
        )
        self._selected_repo_paths = set(self._configured_repo_paths)
        self._render_repository_list()
        self._update_scan_state_result()
        return True

    def _handle_save_success_modal_quit(self, should_quit: bool | None) -> None:
        """Process the save-success dialog decision.

        Args:
            should_quit: True when user selects the quit action.
        """
        if should_quit:
            self.exit()
            return
        if self._displayed_repos and not self._loading:
            self.query_one("#repo-list", OptionList).focus()

    def action_save(self) -> None:
        """Save pending config changes and display success options."""
        if self._loading:
            return
        has_changes = self._has_unsaved_changes()
        if has_changes:
            self._save_changes()
            state_synced = self._sync_config_state_after_save()
            message = (
                "Changes Saved Successfully." if state_synced else "Changes Saved. Reload Failed."
            )
        else:
            message = "No Changes To Save."
        self.push_screen(SaveSuccessModal(message), self._handle_save_success_modal_quit)

    def action_refresh_scan(self) -> None:
        """Force a fresh filesystem scan and bypass the cache."""
        if self._loading:
            return

        self._loading = True
        self.query_one("#repo-list", OptionList).disabled = True

        # Switch the UI back to a loading state
        scan_state_result = self.query_one("#scan-state-result", Label)
        scan_state_result.display = False
        self.query_one("#scan-state-indicator", LoadingIndicator).display = True

        self._set_scan_state_text(full=f"Scanning: {self._discover_root}", compact="Scanning...")

        # Trigger the worker thread with force_scan=True
        self.load_repository_data(force_scan=True)

    def _repos_to_add(self) -> set[Path]:
        """Return selected repositories that are not yet configured."""
        return self._selected_repo_paths - self._configured_repo_paths

    def _repos_to_remove(self) -> set[Path]:
        """Return configured displayed repositories that are now unselected."""
        configured_repos_in_list = self._configured_repo_paths.intersection(self._displayed_repos)
        return configured_repos_in_list - self._selected_repo_paths

    def _has_unsaved_changes(self) -> bool:
        """Return whether current selection differs from persisted config."""
        return bool(self._repos_to_add() or self._repos_to_remove())

    def _handle_unsaved_changes_modal_quit(self, should_quit: bool | None) -> None:
        """Process the unsaved-changes quit dialog decision.

        Args:
            should_quit: True when user confirms quitting without saving.
        """
        if should_quit:
            self.exit()
            return
        if self._displayed_repos and not self._loading:
            self.query_one("#repo-list", OptionList).focus()

    def action_quit_without_saving(self) -> None:
        """Exit immediately or ask for confirmation when unsaved changes exist."""
        if not self._has_unsaved_changes():
            self.exit()
            return
        self.push_screen(UnsavedChangesModal(), self._handle_unsaved_changes_modal_quit)

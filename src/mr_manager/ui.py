"""Textual UI for selecting repositories to add or remove."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Label, LoadingIndicator, OptionList, Static

from mr_manager.config import parse_configured_repo_sections, write_config_updates
from mr_manager.discovery import discover_git_repositories


class MrManagerApp(App[None]):
    """Single-view app to toggle repository membership in myrepos config."""

    TITLE = "mr-manager"
    CSS_PATH = "ui.tcss"

    BINDINGS = [
        ("space", "toggle_selected", "Toggle"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("s", "save", "Save"),
        ("q", "quit_without_saving", "Quit"),
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

    @work(thread=True, exclusive=True)
    def load_repository_data(self) -> None:
        """Load discovered repositories and configured repo sections in a worker."""
        try:
            discovered = discover_git_repositories(self._discover_root)
            sections_by_path = parse_configured_repo_sections(self._config_path)
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
        error_label.update(f"Error Loading Repositories: {error}")
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

    def _render_repo_prompt(self, repo: Path) -> str:
        """Render a single repository row with selected/unselected bullet.

        Args:
            repo: Repository path to render.

        Returns:
            Display string for the repository list row.
        """
        if self._is_missing_or_unreachable(repo):
            bullet = "◐" if repo in self._selected_repo_paths else "◌"
        else:
            bullet = "●" if repo in self._selected_repo_paths else "○"
        return f"{bullet} {repo}"

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
        status_line = self.query_one("#scan-state-result", Label)

        if not self._displayed_repos:
            status_line.update(f"No Git repositories found under {self._discover_root}.")
            return

        discovered_set = self._discovered_repo_set()
        configured_repos_in_list = self._configured_repo_paths.intersection(self._displayed_repos)
        add_count = len(self._selected_repo_paths - self._configured_repo_paths)
        remove_count = len(configured_repos_in_list - self._selected_repo_paths)
        missing_count = len(self._configured_repo_paths - discovered_set)
        status_line.update(
            "Discovered: "
            f"{len(self._discovered_repos)} | Missing: {missing_count} | "
            f"To Add: {add_count} | To Remove: {remove_count}"
        )

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
        configured_repos_in_list = self._configured_repo_paths.intersection(self._displayed_repos)
        repos_to_add = sorted(
            self._selected_repo_paths - self._configured_repo_paths,
            key=lambda repo: str(repo).lower(),
        )
        repos_to_remove = sorted(
            configured_repos_in_list - self._selected_repo_paths,
            key=lambda repo: str(repo).lower(),
        )
        section_names_to_remove = {
            section_name
            for repo in repos_to_remove
            for section_name in self._repo_sections_by_path.get(repo, [])
        }

        if repos_to_add or section_names_to_remove:
            write_config_updates(self._config_path, repos_to_add, section_names_to_remove)

    def action_save(self) -> None:
        """Save pending config changes and exit the application."""
        if self._loading:
            return
        self._save_changes()
        self.exit()

    def action_quit_without_saving(self) -> None:
        """Exit the application without persisting pending changes."""
        self.exit()

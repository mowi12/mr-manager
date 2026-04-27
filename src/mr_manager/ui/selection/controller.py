"""Controller logic for repository selection UI interactions."""

from __future__ import annotations

from pathlib import Path

from mr_manager.core.cache import load_cached_repositories, save_cached_repositories
from mr_manager.core.config import parse_configured_repo_sections, write_config_updates
from mr_manager.core.discovery import discover_git_repositories
from mr_manager.core.user_config import UserConfig, load_user_config
from mr_manager.ui.selection.model import RepositorySelectionModel


class RepositorySelectionController:
    """Coordinate model updates and core repository/config operations."""

    def __init__(self, model: RepositorySelectionModel | None = None) -> None:
        """Initialize the controller with a model instance."""
        self.model = model if model is not None else RepositorySelectionModel()

    def load_repository_data(
        self, force_scan: bool = False
    ) -> tuple[list[Path], dict[Path, list[str]], str | None]:
        """Load discovered repositories and configured repo sections."""
        config_warning: str | None = None
        try:
            self.apply_user_config(load_user_config())
        except (OSError, ValueError) as error:
            config_warning = f"Config Load Failed: {error}"

        sections_by_path = parse_configured_repo_sections(self.model.config_path)

        discovered = None
        if not force_scan:
            discovered = load_cached_repositories(self.model.discovery_cache_ttl_hours)

        if discovered is None:
            discovered = discover_git_repositories(self.model.discover_root)
            save_cached_repositories(discovered)

        return discovered, sections_by_path, config_warning

    def get_current_user_config(self) -> UserConfig:
        """Return current model settings in persistent user-config shape."""
        return UserConfig(
            discovery_cache_ttl_hours=self.model.discovery_cache_ttl_hours,
            discovery_root=self.model.discover_root,
        )

    def apply_user_config(self, user_config: UserConfig) -> None:
        """Apply user-config values to controller model state."""
        self.model.discovery_cache_ttl_hours = user_config.discovery_cache_ttl_hours
        self.model.discover_root = user_config.discovery_root

    def apply_repository_data(
        self, discovered: list[Path], sections_by_path: dict[Path, list[str]]
    ) -> None:
        """Apply loaded repository and config data to model state."""
        self.model.discovered_repos = discovered
        self.model.repo_sections_by_path = sections_by_path
        self.model.configured_repo_paths = set(sections_by_path.keys())
        self._rebuild_displayed_repositories()
        self.model.selected_repo_paths = set(self.model.configured_repo_paths)

    def is_repo_toggled(self, repo: Path) -> bool:
        """Return whether repository selection differs from persisted config."""
        is_selected = repo in self.model.selected_repo_paths
        is_configured = repo in self.model.configured_repo_paths
        return is_selected != is_configured

    def is_missing_or_unreachable(self, repo: Path) -> bool:
        """Return whether a configured repo is absent from discovery results."""
        return (
            repo in self.model.configured_repo_paths
            and repo not in self.model.discovered_repo_set()
        )

    def toggle_repo_by_index(self, index: int) -> Path | None:
        """Toggle selected state for a repository at displayed index."""
        if index < 0 or index >= len(self.model.displayed_repos):
            return None

        repo = self.model.displayed_repos[index]
        if repo in self.model.selected_repo_paths:
            self.model.selected_repo_paths.remove(repo)
        else:
            self.model.selected_repo_paths.add(repo)
        return repo

    def repos_to_add(self) -> set[Path]:
        """Return selected repositories that are not yet configured."""
        return self.model.selected_repo_paths - self.model.configured_repo_paths

    def repos_to_remove(self) -> set[Path]:
        """Return configured displayed repositories that are now unselected."""
        configured_repos_in_list = self.model.configured_repo_paths.intersection(
            self.model.displayed_repos
        )
        return configured_repos_in_list - self.model.selected_repo_paths

    def has_unsaved_changes(self) -> bool:
        """Return whether current selection differs from persisted config."""
        return bool(self.repos_to_add() or self.repos_to_remove())

    def save_changes(self) -> None:
        """Persist selected repository additions/removals to config file."""
        repos_to_add = sorted(self.repos_to_add(), key=lambda repo: str(repo).lower())
        repos_to_remove = sorted(self.repos_to_remove(), key=lambda repo: str(repo).lower())
        section_names_to_remove = {
            section_name
            for repo in repos_to_remove
            for section_name in self.model.repo_sections_by_path.get(repo, [])
        }

        if repos_to_add or section_names_to_remove:
            write_config_updates(self.model.config_path, repos_to_add, section_names_to_remove)

    def refresh_config_state_after_save(self) -> None:
        """Reload configured repositories from disk into model state."""
        sections_by_path = parse_configured_repo_sections(self.model.config_path)
        self.model.repo_sections_by_path = sections_by_path
        self.model.configured_repo_paths = set(sections_by_path.keys())
        self._rebuild_displayed_repositories()
        self.model.selected_repo_paths = set(self.model.configured_repo_paths)

    def _rebuild_displayed_repositories(self) -> None:
        """Rebuild displayed repository list from discovered and configured sets."""
        discovered_set = self.model.discovered_repo_set()
        self.model.displayed_repos = sorted(
            discovered_set.union(self.model.configured_repo_paths),
            key=lambda repo: str(repo).lower(),
        )

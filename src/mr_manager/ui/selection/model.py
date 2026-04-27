"""Model classes for mr-manager UI state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RepositorySelectionModel:
    """State model for repository selection and scan status."""

    discover_root: Path = field(default_factory=Path.home)
    config_path: Path = field(default_factory=lambda: Path.home() / ".mrconfig")
    discovered_repos: list[Path] = field(default_factory=list)
    displayed_repos: list[Path] = field(default_factory=list)
    repo_sections_by_path: dict[Path, list[str]] = field(default_factory=dict)
    configured_repo_paths: set[Path] = field(default_factory=set)
    selected_repo_paths: set[Path] = field(default_factory=set)
    loading: bool = True
    scan_state_text: str = ""
    scan_state_text_compact: str | None = None

    def discovered_repo_set(self) -> set[Path]:
        """Return discovered repositories as a set for membership checks."""
        return set(self.discovered_repos)

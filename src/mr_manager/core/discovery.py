"""Repository discovery helpers for filesystem scanning."""

from __future__ import annotations

import os
from pathlib import Path

_IGNORED_DISCOVERY_DIRS = {
    "Library",
    "Applications",
    "Movies",
    "Music",
    "Pictures",
    "Downloads",
    "Public",
    ".Trash",
    ".cache",
    ".local",
    ".npm",
    ".cargo",
    ".rustup",
    "node_modules",
    ".venv",
    "venv",
}


def _should_descend_directory(directory_name: str) -> bool:
    """Return whether a directory should be traversed during repository discovery.

    Args:
        directory_name: Candidate child directory name from os.walk.

    Returns:
        True when the directory should be traversed, otherwise False.
    """
    if directory_name in {".", ".."}:
        return False
    return directory_name not in _IGNORED_DISCOVERY_DIRS


def discover_git_repositories(root: Path) -> list[Path]:
    """Mocked repository discovery for screenshots."""
    base_dir = Path("/Users/moritz")
    repo_paths =[
        base_dir / "experiments" / "data-pipeline",
        base_dir / "experiments" / "dev-environment",
        base_dir / "experiments" / "ml-models",
        base_dir / "experiments" / "scripts",
        base_dir / "open-source" / "cli-tools",
        base_dir / "open-source" / "component-library",
        base_dir / "open-source" / "docs-site",
        base_dir / "open-source" / "shared-utils",
        base_dir / "projects" / "frontend-app",
        base_dir / "projects" / "landing-page",
        base_dir / "projects" / "mobile-app",
        base_dir / "projects" / "web-client",
        base_dir / "work" / "api-service",
        base_dir / "work" / "auth-backend",
        base_dir / "work" / "infrastructure",
        base_dir / "work" / "payment-gateway",
    ]
    return sorted(repo_paths)

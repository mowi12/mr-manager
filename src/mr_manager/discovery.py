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
    """Discover Git repositories recursively below a root directory.

    Args:
        root: Filesystem directory used as scan root.

    Returns:
        Sorted absolute repository paths where a `.git` directory exists.
    """
    discovered: list[Path] = []
    for current_root, dirs, _ in os.walk(root, topdown=True):
        if ".git" in dirs:
            discovered.append(Path(current_root).resolve())
            # Repo detected: skip descending into its working tree for speed.
            dirs.clear()
            continue

        dirs[:] = [directory for directory in dirs if _should_descend_directory(directory)]

    return sorted(discovered, key=lambda repo: str(repo).lower())

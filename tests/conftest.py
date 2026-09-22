"""Shared fixtures for the mr-manager test suite."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def make_git_repo() -> Callable[[Path], Path]:
    """Return a factory creating a directory that looks like a Git checkout."""

    def _make(path: Path, *, as_file: bool = False) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        git_marker = path / ".git"
        if as_file:
            # Worktrees and submodules use a `.git` file pointing at the real gitdir.
            git_marker.write_text("gitdir: /elsewhere/.git/worktrees/x\n", encoding="utf-8")
        else:
            git_marker.mkdir(exist_ok=True)
        return path

    return _make


@pytest.fixture
def make_real_git_repo() -> Callable[..., Path]:
    """Return a factory creating an initialized Git repository on disk."""

    def _make(path: Path, *, origin: str | None = None) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        if origin is not None:
            subprocess.run(
                ["git", "-C", str(path), "remote", "add", "origin", origin],
                check=True,
            )
        return path

    return _make

"""Shared fixtures for the mr-manager test suite."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from mr_manager.core import cache, user_config


@pytest.fixture(autouse=True)
def isolated_environment(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Keep every test away from the real home directory and Git configuration.

    `HOME` is redirected to a temporary directory. Paths that modules compute from the
    home directory at import time are re-pointed there as well, so no test can read or
    write the user's real `.mrconfig`, discovery cache or mr-manager config.

    Git environment variables are cleared and global/system Git config is disabled, so
    `git` subprocesses behave the same on every machine and can never act on an outer
    repository (for example when the suite runs from inside a Git hook).

    Returns:
        The temporary home directory.
    """
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(
        cache, "_CACHE_FILE", home / ".cache" / "mr-manager" / "discovery_cache.json"
    )
    monkeypatch.setattr(user_config, "_DEFAULT_DISCOVERY_ROOT", home)
    monkeypatch.setattr(
        user_config, "_USER_CONFIG_PATH", home / ".config" / "mr-manager" / "config.yaml"
    )

    for name in list(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    return home


@pytest.fixture
def make_git_repo() -> Callable[[Path], Path]:
    """Return a factory creating a directory that looks like a Git checkout."""

    def _make(path: Path) -> Path:
        (path / ".git").mkdir(parents=True, exist_ok=True)
        return path

    return _make


@pytest.fixture
def make_real_git_repo() -> Callable[..., Path]:
    """Return a factory creating an initialized Git repository on disk."""

    def _make(path: Path, *, origin: str | None = None) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
        if origin is not None:
            subprocess.run(["git", "-C", str(path), "remote", "add", "origin", origin], check=True)
        return path

    return _make

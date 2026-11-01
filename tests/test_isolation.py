"""Guards for the suite-wide isolation fixture."""

from __future__ import annotations

import os
from pathlib import Path

from mr_manager.core import cache, user_config
from mr_manager.ui.selection.model import RepositorySelectionModel


def test_home_and_derived_paths_point_into_the_temporary_home(isolated_environment: Path) -> None:
    assert Path.home() == isolated_environment
    assert cache._CACHE_FILE.is_relative_to(isolated_environment)
    assert user_config.get_user_config_path().is_relative_to(isolated_environment)
    assert RepositorySelectionModel().config_path == isolated_environment / ".mrconfig"


def test_git_environment_is_neutralized() -> None:
    assert os.environ["GIT_CONFIG_GLOBAL"] == os.devnull
    assert os.environ["GIT_CONFIG_NOSYSTEM"] == "1"
    assert "GIT_DIR" not in os.environ

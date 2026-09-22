"""Tests for repository selection controller logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from mr_manager.core.user_config import UserConfig
from mr_manager.ui.selection.controller import RepositorySelectionController
from mr_manager.ui.selection.model import RepositorySelectionModel


@pytest.fixture
def controller(tmp_path: Path) -> RepositorySelectionController:
    """Return a controller seeded with two discovered and one configured repo."""
    instance = RepositorySelectionController(RepositorySelectionModel())
    instance.model.config_path = tmp_path / ".mrconfig"
    alpha, beta = tmp_path / "alpha", tmp_path / "beta"
    instance.apply_repository_data([alpha, beta], {alpha: ["alpha"]})
    return instance


class TestSelectionState:
    """Selection bookkeeping against the configured baseline."""

    def test_configured_repositories_start_selected(
        self, controller: RepositorySelectionController, tmp_path: Path
    ) -> None:
        assert controller.model.selected_repo_paths == {tmp_path / "alpha"}

    def test_freshly_loaded_state_has_no_changes(
        self, controller: RepositorySelectionController
    ) -> None:
        assert controller.has_unsaved_changes() is False
        assert controller.repos_to_add() == set()
        assert controller.repos_to_remove() == set()

    def test_selecting_an_unconfigured_repo_queues_an_addition(
        self, controller: RepositorySelectionController, tmp_path: Path
    ) -> None:
        controller.toggle_repo_by_index(controller.model.displayed_repos.index(tmp_path / "beta"))

        assert controller.repos_to_add() == {tmp_path / "beta"}
        assert controller.has_unsaved_changes() is True

    def test_deselecting_a_configured_repo_queues_a_removal(
        self, controller: RepositorySelectionController, tmp_path: Path
    ) -> None:
        controller.toggle_repo_by_index(controller.model.displayed_repos.index(tmp_path / "alpha"))

        assert controller.repos_to_remove() == {tmp_path / "alpha"}

    def test_toggling_twice_restores_the_baseline(
        self, controller: RepositorySelectionController, tmp_path: Path
    ) -> None:
        index = controller.model.displayed_repos.index(tmp_path / "beta")
        controller.toggle_repo_by_index(index)
        controller.toggle_repo_by_index(index)

        assert controller.has_unsaved_changes() is False

    def test_is_repo_toggled_tracks_divergence_from_config(
        self, controller: RepositorySelectionController, tmp_path: Path
    ) -> None:
        beta = tmp_path / "beta"
        assert controller.is_repo_toggled(beta) is False

        controller.toggle_repo_by_index(controller.model.displayed_repos.index(beta))

        assert controller.is_repo_toggled(beta) is True


class TestToggleBounds:
    """Index guards on `toggle_repo_by_index`."""

    @pytest.mark.parametrize("index", [-1, 2, 99])
    def test_out_of_range_index_is_ignored(
        self, controller: RepositorySelectionController, index: int
    ) -> None:
        assert controller.toggle_repo_by_index(index) is None

    def test_valid_index_returns_the_toggled_repository(
        self, controller: RepositorySelectionController, tmp_path: Path
    ) -> None:
        assert controller.toggle_repo_by_index(0) == tmp_path / "alpha"


class TestDisplayedRepositories:
    """Merging of discovered and configured repositories."""

    def test_configured_but_undiscovered_repos_are_still_displayed(self, tmp_path: Path) -> None:
        instance = RepositorySelectionController(RepositorySelectionModel())
        missing = tmp_path / "missing"
        instance.apply_repository_data([tmp_path / "alpha"], {missing: ["missing"]})

        assert missing in instance.model.displayed_repos
        assert instance.is_missing_or_unreachable(missing) is True

    def test_discovered_repos_are_not_flagged_as_missing(
        self, controller: RepositorySelectionController, tmp_path: Path
    ) -> None:
        assert controller.is_missing_or_unreachable(tmp_path / "alpha") is False

    def test_displayed_repositories_are_sorted_case_insensitively(self, tmp_path: Path) -> None:
        instance = RepositorySelectionController(RepositorySelectionModel())
        instance.apply_repository_data(
            [tmp_path / "Beta", tmp_path / "alpha"], {tmp_path / "Gamma": ["Gamma"]}
        )

        assert [p.name for p in instance.model.displayed_repos] == ["alpha", "Beta", "Gamma"]


class TestSaveChanges:
    """Persisting queued additions and removals."""

    def test_queued_addition_is_written_to_config(self, tmp_path: Path, make_real_git_repo) -> None:
        instance = RepositorySelectionController(RepositorySelectionModel())
        instance.model.config_path = tmp_path / ".mrconfig"
        repo = make_real_git_repo(tmp_path / "alpha", origin="https://example.com/a.git")
        instance.apply_repository_data([repo], {})
        instance.toggle_repo_by_index(0)

        instance.save_changes()

        assert "[alpha]" in instance.model.config_path.read_text(encoding="utf-8")

    def test_saving_without_changes_leaves_config_untouched(
        self, controller: RepositorySelectionController
    ) -> None:
        controller.save_changes()

        assert controller.model.config_path.exists() is False

    def test_refresh_after_save_resets_the_baseline(
        self, tmp_path: Path, make_real_git_repo
    ) -> None:
        instance = RepositorySelectionController(RepositorySelectionModel())
        instance.model.config_path = tmp_path / ".mrconfig"
        repo = make_real_git_repo(tmp_path / "alpha", origin="https://example.com/a.git")
        instance.apply_repository_data([repo], {})
        instance.toggle_repo_by_index(0)
        instance.save_changes()

        instance.refresh_config_state_after_save()

        assert instance.has_unsaved_changes() is False


class TestLoadRepositoryData:
    """Cache and scan coordination in `load_repository_data`."""

    @pytest.fixture
    def instance(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Return a controller with a pinned user config and no config file."""
        controller = RepositorySelectionController(RepositorySelectionModel())
        controller.model.config_path = tmp_path / ".mrconfig"
        monkeypatch.setattr(
            "mr_manager.ui.selection.controller.load_user_config",
            lambda: UserConfig(discovery_cache_ttl_hours=24, discovery_root=tmp_path / "root"),
        )
        return controller

    def test_cache_lookup_is_scoped_to_the_discovery_root(
        self, instance, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Path] = {}
        monkeypatch.setattr(
            "mr_manager.ui.selection.controller.load_cached_repositories",
            lambda root, _ttl: seen.setdefault("root", root) and None,
        )
        monkeypatch.setattr(
            "mr_manager.ui.selection.controller.discover_git_repositories", lambda _root: []
        )
        monkeypatch.setattr(
            "mr_manager.ui.selection.controller.save_cached_repositories",
            lambda *_args: None,
        )

        instance.load_repository_data()

        assert seen["root"] == tmp_path / "root"

    def test_scan_results_are_cached_under_the_same_root(
        self, instance, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        saved: dict[str, Path] = {}
        monkeypatch.setattr(
            "mr_manager.ui.selection.controller.load_cached_repositories",
            lambda _root, _ttl: None,
        )
        monkeypatch.setattr(
            "mr_manager.ui.selection.controller.discover_git_repositories",
            lambda root: [root / "alpha"],
        )
        monkeypatch.setattr(
            "mr_manager.ui.selection.controller.save_cached_repositories",
            lambda _repos, root: saved.setdefault("root", root),
        )

        discovered, _sections, warning = instance.load_repository_data()

        assert saved["root"] == tmp_path / "root"
        assert discovered == [tmp_path / "root" / "alpha"]
        assert warning is None

    def test_forced_scan_bypasses_the_cache(
        self, instance, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _fail(*_args: object) -> None:
            raise AssertionError("cache must not be consulted during a forced scan")

        monkeypatch.setattr("mr_manager.ui.selection.controller.load_cached_repositories", _fail)
        monkeypatch.setattr(
            "mr_manager.ui.selection.controller.discover_git_repositories", lambda _root: []
        )
        monkeypatch.setattr(
            "mr_manager.ui.selection.controller.save_cached_repositories", lambda *_a: None
        )

        instance.load_repository_data(force_scan=True)

    def test_failed_user_config_load_is_reported_as_a_warning(
        self, instance, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise() -> None:
            raise OSError("permission denied")

        monkeypatch.setattr("mr_manager.ui.selection.controller.load_user_config", _raise)
        monkeypatch.setattr(
            "mr_manager.ui.selection.controller.load_cached_repositories",
            lambda _root, _ttl: [],
        )

        _discovered, _sections, warning = instance.load_repository_data()

        assert warning is not None
        assert "permission denied" in warning

"""Tests for filesystem repository discovery."""

from __future__ import annotations

from pathlib import Path

from mr_manager.core.discovery import discover_git_repositories


class TestDiscovery:
    """Behavior of `discover_git_repositories`."""

    def test_empty_root_yields_no_repositories(self, tmp_path: Path) -> None:
        assert discover_git_repositories(tmp_path) == []

    def test_absent_root_yields_no_repositories(self, tmp_path: Path) -> None:
        assert discover_git_repositories(tmp_path / "absent") == []

    def test_nested_repositories_are_found(self, tmp_path: Path, make_git_repo) -> None:
        alpha = make_git_repo(tmp_path / "a" / "alpha")
        beta = make_git_repo(tmp_path / "b" / "c" / "beta")

        assert discover_git_repositories(tmp_path) == [alpha, beta]

    def test_repository_working_tree_is_not_descended_into(
        self, tmp_path: Path, make_git_repo
    ) -> None:
        outer = make_git_repo(tmp_path / "outer")
        make_git_repo(outer / "vendor" / "inner")

        assert discover_git_repositories(tmp_path) == [outer]

    def test_ignored_directories_are_pruned(self, tmp_path: Path, make_git_repo) -> None:
        make_git_repo(tmp_path / "node_modules" / "pkg")
        make_git_repo(tmp_path / ".venv" / "src")
        kept = make_git_repo(tmp_path / "kept")

        assert discover_git_repositories(tmp_path) == [kept]

    def test_results_are_sorted_case_insensitively(self, tmp_path: Path, make_git_repo) -> None:
        make_git_repo(tmp_path / "Beta")
        make_git_repo(tmp_path / "alpha")
        make_git_repo(tmp_path / "Gamma")

        assert [p.name for p in discover_git_repositories(tmp_path)] == [
            "alpha",
            "Beta",
            "Gamma",
        ]

    def test_symlink_loop_terminates(self, tmp_path: Path, make_git_repo) -> None:
        repo = make_git_repo(tmp_path / "repo")
        (tmp_path / "loop").symlink_to(tmp_path, target_is_directory=True)

        assert discover_git_repositories(tmp_path) == [repo]

"""Tests for discovery cache persistence."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from mr_manager.core import cache
from mr_manager.core.cache import load_cached_repositories, save_cached_repositories

requires_permissions = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores directory permissions",
)


@pytest.fixture
def cache_file() -> Path:
    """Return the cache file location the isolation fixture points the module at."""
    return cache._CACHE_FILE


@pytest.fixture
def read_only_dir(tmp_path: Path) -> Iterator[Path]:
    """Return a directory nobody may write into, restoring access afterwards."""
    path = tmp_path / "read-only"
    path.mkdir()
    path.chmod(0o555)
    yield path
    path.chmod(0o755)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Return a discovery root for cache entries."""
    return tmp_path / "root"


def _write_envelope(cache_file: Path, root: Path, repositories: object) -> None:
    """Write a current-format cache file by hand."""
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "root": cache._normalize_root(root), "repositories": repositories}
    cache_file.write_text(json.dumps(payload), encoding="utf-8")


class TestRoundTrip:
    """Saving and loading the cache."""

    def test_saved_repositories_are_loaded_back(self, tmp_path: Path, root: Path) -> None:
        repositories = [tmp_path / "alpha", tmp_path / "beta"]

        save_cached_repositories(repositories, root)

        assert load_cached_repositories(root) == repositories

    def test_empty_repository_list_round_trips(self, root: Path) -> None:
        save_cached_repositories([], root)

        assert load_cached_repositories(root) == []

    def test_parent_directory_is_created(self, cache_file: Path, root: Path) -> None:
        save_cached_repositories([], root)

        assert cache_file.exists()


@requires_permissions
class TestUnwritableLocation:
    """A cache that cannot be written must never break the caller."""

    def test_unwritable_cache_directory_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch, read_only_dir: Path, tmp_path: Path, root: Path
    ) -> None:
        monkeypatch.setattr(cache, "_CACHE_FILE", read_only_dir / "cache.json")

        save_cached_repositories([tmp_path / "alpha"], root)  # must not raise

    def test_uncreatable_cache_directory_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch, read_only_dir: Path, tmp_path: Path, root: Path
    ) -> None:
        monkeypatch.setattr(cache, "_CACHE_FILE", read_only_dir / "mr-manager" / "cache.json")

        save_cached_repositories([tmp_path / "alpha"], root)  # must not raise


class TestRootKeying:
    """The cache must only be reused for the root that produced it."""

    def test_cache_from_a_different_root_is_a_miss(self, tmp_path: Path) -> None:
        save_cached_repositories([tmp_path / "alpha"], tmp_path / "first")

        assert load_cached_repositories(tmp_path / "second") is None

    def test_equivalent_root_spellings_hit_the_same_entry(self, tmp_path: Path) -> None:
        repositories = [tmp_path / "alpha"]
        save_cached_repositories(repositories, tmp_path / "root")

        assert load_cached_repositories(tmp_path / "." / "root") == repositories

    def test_home_relative_root_is_normalized(self) -> None:
        repositories = [Path.home() / "projects" / "alpha"]
        save_cached_repositories(repositories, Path("~/projects"))

        assert load_cached_repositories(Path.home() / "projects") == repositories


class TestCacheMisses:
    """Conditions that must be treated as a cache miss rather than an error."""

    def test_absent_file_is_a_miss(self, root: Path) -> None:
        assert load_cached_repositories(root) is None

    def test_corrupt_json_is_a_miss(self, cache_file: Path, root: Path) -> None:
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text("{not json", encoding="utf-8")

        assert load_cached_repositories(root) is None

    @pytest.mark.parametrize(
        "payload", [5, None, "/a", {"/a": 1}], ids=["int", "null", "string", "object"]
    )
    def test_valid_json_that_is_not_a_cache_envelope_is_a_miss(
        self, cache_file: Path, payload: object, root: Path
    ) -> None:
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(json.dumps(payload), encoding="utf-8")

        assert load_cached_repositories(root) is None

    def test_legacy_bare_list_format_is_a_miss(self, cache_file: Path, root: Path) -> None:
        # Earlier versions cached a bare list that did not record the discovery root.
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(json.dumps(["/a", "/b"]), encoding="utf-8")

        assert load_cached_repositories(root) is None

    def test_unknown_schema_version_is_a_miss(self, cache_file: Path, root: Path) -> None:
        cache_file.parent.mkdir(parents=True)
        payload = {"version": 99, "root": cache._normalize_root(root), "repositories": []}
        cache_file.write_text(json.dumps(payload), encoding="utf-8")

        assert load_cached_repositories(root) is None

    def test_malformed_repository_list_is_a_miss(self, cache_file: Path, root: Path) -> None:
        _write_envelope(cache_file, root, "not a list")

        assert load_cached_repositories(root) is None

    def test_non_string_entries_are_dropped(self, cache_file: Path, root: Path) -> None:
        _write_envelope(cache_file, root, ["/a", 5, None, "/b"])

        assert load_cached_repositories(root) == [Path("/a"), Path("/b")]


class TestExpiration:
    """TTL handling."""

    def test_fresh_cache_is_returned(self, tmp_path: Path, root: Path) -> None:
        save_cached_repositories([tmp_path / "alpha"], root)

        assert load_cached_repositories(root, cache_ttl_hours=24) == [tmp_path / "alpha"]

    def test_expired_cache_is_a_miss(self, cache_file: Path, tmp_path: Path, root: Path) -> None:
        save_cached_repositories([tmp_path / "alpha"], root)
        stale = time.time() - (25 * 3600)
        os.utime(cache_file, (stale, stale))

        assert load_cached_repositories(root, cache_ttl_hours=24) is None

    @pytest.mark.parametrize("ttl_hours", [0, -1])
    def test_non_positive_ttl_is_rejected(self, ttl_hours: int, root: Path) -> None:
        with pytest.raises(ValueError, match="cache_ttl_hours must be greater than 0"):
            load_cached_repositories(root, cache_ttl_hours=ttl_hours)

"""Tests for discovery cache persistence."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from mr_manager.core import cache
from mr_manager.core.cache import load_cached_repositories, save_cached_repositories


@pytest.fixture(autouse=True)
def cache_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the module-level cache file into a temporary directory."""
    path = tmp_path / "cache" / "discovery_cache.json"
    monkeypatch.setattr(cache, "_CACHE_FILE", path)
    return path


class TestRoundTrip:
    """Saving and loading the cache."""

    def test_saved_repositories_are_loaded_back(self, tmp_path: Path) -> None:
        repositories = [tmp_path / "alpha", tmp_path / "beta"]

        save_cached_repositories(repositories)

        assert load_cached_repositories() == repositories

    def test_empty_repository_list_round_trips(self) -> None:
        save_cached_repositories([])

        assert load_cached_repositories() == []

    def test_parent_directory_is_created(self, cache_file: Path) -> None:
        save_cached_repositories([])

        assert cache_file.exists()

    def test_unwritable_cache_location_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(cache, "_CACHE_FILE", tmp_path / "dir" / "cache.json")
        monkeypatch.setattr(
            Path, "write_text", lambda *_a, **_k: (_ for _ in ()).throw(OSError("read-only"))
        )

        save_cached_repositories([tmp_path / "alpha"])  # must not raise


class TestCacheMisses:
    """Conditions that must be treated as a cache miss rather than an error."""

    def test_absent_file_is_a_miss(self) -> None:
        assert load_cached_repositories() is None

    def test_corrupt_json_is_a_miss(self, cache_file: Path) -> None:
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text("{not json", encoding="utf-8")

        assert load_cached_repositories() is None

    def test_non_string_entries_are_dropped(self, cache_file: Path) -> None:
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(json.dumps(["/a", 5, None, "/b"]), encoding="utf-8")

        assert load_cached_repositories() == [Path("/a"), Path("/b")]


class TestExpiration:
    """TTL handling."""

    def test_fresh_cache_is_returned(self, tmp_path: Path) -> None:
        save_cached_repositories([tmp_path / "alpha"])

        assert load_cached_repositories(cache_ttl_hours=24) == [tmp_path / "alpha"]

    def test_expired_cache_is_a_miss(self, cache_file: Path, tmp_path: Path) -> None:
        save_cached_repositories([tmp_path / "alpha"])
        stale = time.time() - (25 * 3600)
        import os

        os.utime(cache_file, (stale, stale))

        assert load_cached_repositories(cache_ttl_hours=24) is None

    @pytest.mark.parametrize("ttl_hours", [0, -1])
    def test_non_positive_ttl_is_rejected(self, ttl_hours: int) -> None:
        with pytest.raises(ValueError, match="cache_ttl_hours must be greater than 0"):
            load_cached_repositories(cache_ttl_hours=ttl_hours)
